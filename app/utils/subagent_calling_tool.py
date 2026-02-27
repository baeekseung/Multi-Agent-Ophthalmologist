from typing import Annotated, NotRequired

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import TypedDict

from app.state import DeepAgentState
from app.utils.logger import get_logger

logger = get_logger(__name__)

TASK_DESCRIPTION_PREFIX = """Delegate a task to a specialized sub-agent with isolated context. Available agents for delegation are:
{other_agents}
"""

class SubAgent(TypedDict):
    """Configuration for a specialized sub-agent."""
    name: str
    description: str
    prompt: str
    tools: NotRequired[list[str]]

def _create_task_tool(tools, subagents: list[SubAgent], model, state_schema):
    """Create a task delegation tool that enables context isolation through sub-agents.

    This function implements the core pattern for spawning specialized sub-agents with
    isolated contexts, preventing context clash and confusion in complex multi-step tasks.

    Args:
        tools: List of available tools that can be assigned to sub-agents
        subagents: List of specialized sub-agent configurations
        model: The language model to use for all agents
        state_schema: The state schema (typically DeepAgentState)

    Returns:
        A 'task' tool that can delegate work to specialized sub-agents
    """
    agents = {}
    tools_by_name = {}

    for tool_ in tools:
        if not isinstance(tool_, BaseTool):
            tool_ = tool(tool_)
        tools_by_name[tool_.name] = tool_

    # Sub-agent 구성 정보 기반으로 특화 에이전트 생성 및 레지스트리에 등록
    for _agent in subagents:
        if "tools" in _agent:
            # Sub-agent에 지정된 도구만 할당
            _tools = [tools_by_name[t] for t in _agent["tools"]]
        else:
            # 도구 미지정 시 전체 도구 할당
            _tools = tools
        agents[_agent["name"]] = create_agent( 
            model,
            system_prompt=_agent["prompt"],
            tools=_tools,
            state_schema=state_schema,
        )

    # 사용 가능한 Sub-agent 목록을 도구 설명에 활용하기 위한 문자열 리스트 생성
    other_agents_string = [
        f"- {_agent['name']}: {_agent['description']}" for _agent in subagents
    ]

    @tool(description=TASK_DESCRIPTION_PREFIX.format(other_agents=other_agents_string))
    def task(
        description: str,
        subagent_type: str,
        state: Annotated[DeepAgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ):
        """특정 작업을 전문화된 서브 에이전트에게 위임하여 실행하는 도구. 위임할 서브에이전트의 이름과 작업 설명을 제공하면 해당 서브에이전트가 작업을 수행하고 결과를 반환합니다.
        서브 에이전트가 작업을 수행하고 결과를 반환하면, 그 결과를 부모 에이전트에 ToolMessage 형태로 반환합니다.

        Args:
            description: 작업 설명(명확하고 구체적인 작업 내용을 포함하는 문자열)
            subagent_type: 위임할 서브에이전트의 이름(레지스트리에 등록된 서브에이전트의 이름)

        Returns:
            Command: 작업 결과를 포함한 상태 업데이트 명령
        """
        # 요청된 Sub-agent 타입이 레지스트리에 존재하는지 검증, 미존재 시 에러 반환
        if subagent_type not in agents:
            logger.error(f"[TASK] 알 수 없는 서브에이전트: '{subagent_type}' (허용: {list(agents.keys())})")
            return f"Error: invoked agent of type {subagent_type}, the only allowed types are {[f'`{k}`' for k in agents]}"

        # 요청된 Sub-agent 인스턴스 가져오기
        sub_agent = agents[subagent_type]

        logger.info(f"[TASK] → {subagent_type} 위임 시작")
        logger.debug(f"[TASK] description: {description[:300]}{'...' if len(description) > 300 else ''}")

        # 작업 설명만 포함된 격리된 컨텍스트 생성, 부모 에이전트의 히스토리 미포함
        # HumanMessage 객체 사용 (일반 dict는 LangChain 메시지 검증 실패)
        new_state = {
            "messages": [HumanMessage(content=description)],
            "files": state.get("files", {}),
            "todos": state.get("todos", []),
        }

        # 격리된 환경에서 Sub-agent 실행 및 결과 획득
        result = sub_agent.invoke(new_state)

        saved_files = list(result.get("files", {}).keys())
        logger.info(f"[TASK] ← {subagent_type} 완료" + (f" | 저장된 파일: {saved_files}" if saved_files else ""))

        # 작업 결과를 Command 객체로 래핑하여 부모 에이전트에 ToolMessage 형태로 반환
        return Command(
            update={
                "files": result.get("files", {}),  # 파일 변경 사항 병합
                "messages": [
                    # Sub-agent의 마지막 메시지를 ToolMessage로 변환하여 반환
                    ToolMessage(
                        result["messages"][-1].content, tool_call_id=tool_call_id
                    )
                ],
            }
        )

    return task