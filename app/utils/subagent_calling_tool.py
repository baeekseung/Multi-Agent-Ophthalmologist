import asyncio
from typing import Annotated, NotRequired

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import TypedDict

# langgraph-supervisor: 에이전트 설명 자동 생성에 활용
try:
    from langgraph_supervisor.handoff import create_handoff_tool as _lgs_handoff
    _HAS_LGS = True
except ImportError:
    _HAS_LGS = False

from app.state import DeepAgentState
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 서브에이전트 재시도 설정
_MAX_RETRIES = 2
_RETRY_BASE_DELAY = 2.0  # 초 (지수 백오프 기반)

# adispatch_custom_event: langchain_core >= 0.3 에서 지원
try:
    from langchain_core.callbacks.manager import adispatch_custom_event
    _HAS_DISPATCH = True
except ImportError:
    _HAS_DISPATCH = False
    logger.warning("[TASK] adispatch_custom_event 미지원 버전 — 커스텀 이벤트 비활성화")


def _build_task_description(subagents: list) -> str:
    """langgraph-supervisor의 핸드오프 도구 설명 형식을 활용하여
    서브에이전트 목록을 포함한 task 도구 설명을 생성합니다."""
    if _HAS_LGS:
        # 라이브러리 스타일: 각 에이전트 설명을 핸드오프 도구 형식으로 표현
        lines = ["Delegate a task to a specialized sub-agent with isolated context."]
        lines.append("Available agents:")
        for _agent in subagents:
            lines.append(f"  - {_agent['name']}: {_agent['description']}")
        return "\n".join(lines)
    else:
        # 폴백: 기존 방식
        agent_list = "\n".join(f"- {a['name']}: {a['description']}" for a in subagents)
        return f"Delegate a task to a specialized sub-agent with isolated context. Available agents:\n{agent_list}"

class SubAgent(TypedDict):
    """특화 서브에이전트 설정"""
    name: str
    description: str
    prompt: str
    tools: NotRequired[list[str]]

def _create_task_tool(tools, subagents: list[SubAgent], model, state_schema):
    """컨텍스트 격리 서브에이전트 위임 도구 생성.

    복잡한 다단계 작업에서 컨텍스트 충돌을 방지하기 위해
    특화 서브에이전트를 격리된 컨텍스트로 실행하는 패턴을 구현합니다.

    Args:
        tools: 서브에이전트에 할당 가능한 도구 목록
        subagents: 특화 서브에이전트 설정 목록
        model: 모든 에이전트에 사용할 LLM
        state_schema: 상태 스키마 (주로 DeepAgentState)

    Returns:
        서브에이전트에게 작업을 위임하는 'task' 도구
    """
    agents = {}
    tools_by_name = {}

    for tool_ in tools:
        if not isinstance(tool_, BaseTool):
            tool_ = tool(tool_)
        tools_by_name[tool_.name] = tool_

    # 서브에이전트 구성 정보 기반으로 특화 에이전트 생성 및 레지스트리 등록
    for _agent in subagents:
        if "tools" in _agent:
            _tools = [tools_by_name[t] for t in _agent["tools"]]
        else:
            _tools = tools
        agents[_agent["name"]] = create_agent(
            model,
            system_prompt=_agent["prompt"],
            tools=_tools,
            state_schema=state_schema,
        )

    task_description = _build_task_description(subagents)

    @tool(description=task_description)
    async def task(
        description: str,
        subagent_type: str,
        state: Annotated[DeepAgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ):
        """특정 작업을 전문화된 서브 에이전트에게 위임하여 실행하는 도구.
        위임할 서브에이전트의 이름과 작업 설명을 제공하면 해당 서브에이전트가
        작업을 수행하고 결과를 ToolMessage 형태로 반환합니다.

        Args:
            description: 작업 설명 (명확하고 구체적인 작업 내용)
            subagent_type: 위임할 서브에이전트의 이름 (레지스트리에 등록된 이름)

        Returns:
            Command: 작업 결과를 포함한 상태 업데이트 명령
        """
        if subagent_type not in agents:
            logger.error(f"[TASK] 알 수 없는 서브에이전트: '{subagent_type}' (허용: {list(agents.keys())})")
            return f"Error: invoked agent of type {subagent_type}, the only allowed types are {[f'`{k}`' for k in agents]}"

        sub_agent = agents[subagent_type]

        # 서브에이전트 시작 커스텀 이벤트 발송
        if _HAS_DISPATCH:
            await adispatch_custom_event("subagent_start", {
                "event_name": "subagent_start",
                "subagent_type": subagent_type,
                "description": description[:300],
            })

        logger.info(f"[TASK] → {subagent_type} 위임 시작")
        logger.debug(f"[TASK] description: {description[:300]}{'...' if len(description) > 300 else ''}")

        # 격리된 컨텍스트 생성 (부모 에이전트 히스토리 미포함)
        new_state = {
            "messages": [HumanMessage(content=description)],
            "files": state.get("files", {}),
            "todos": state.get("todos", []),
        }

        # 지수 백오프 재시도 (최대 _MAX_RETRIES회)
        result = None
        last_error = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                result = await sub_agent.ainvoke(new_state)
                break
            except Exception as e:
                last_error = e
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"[TASK] {subagent_type} 실패 (시도 {attempt + 1}/{_MAX_RETRIES + 1}), "
                        f"{delay}초 후 재시도: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"[TASK] {subagent_type} 최대 재시도 초과: {e}")

        if result is None:
            # 최대 재시도 후에도 실패 → 부분 결과로 계속 진행 (전체 파이프라인 중단 방지)
            error_msg = f"[서브에이전트 오류] {subagent_type} 실행 실패: {last_error}"
            logger.error(f"[TASK] {error_msg}")
            return Command(
                update={
                    "messages": [ToolMessage(error_msg, tool_call_id=tool_call_id)],
                }
            )

        saved_files = list(result.get("files", {}).keys())
        logger.info(f"[TASK] ← {subagent_type} 완료" + (f" | 저장된 파일: {saved_files}" if saved_files else ""))

        # 서브에이전트 완료 커스텀 이벤트 발송
        if _HAS_DISPATCH:
            await adispatch_custom_event("subagent_complete", {
                "event_name": "subagent_complete",
                "subagent_type": subagent_type,
                "saved_files": saved_files,
            })

        return Command(
            update={
                "files": result.get("files", {}),
                "messages": [
                    ToolMessage(
                        result["messages"][-1].content, tool_call_id=tool_call_id
                    )
                ],
            }
        )

    return task
