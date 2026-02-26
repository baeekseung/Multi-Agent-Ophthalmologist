from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.state import DeepAgentState, Todo
from app.utils.logger import get_logger

logger = get_logger(__name__)


@tool(parse_docstring=True)
def write_todos(
    todos: list[Todo],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """TODO 목록을 작성하거나 업데이트합니다.

    작업 계획을 세우거나 TODO 항목의 상태를 업데이트할 때 사용합니다.
    전체 TODO 목록을 새로운 상태로 교체합니다.

    Args:
        todos: 업데이트된 TODO 항목 목록 (content, status 필드 포함)
        tool_call_id: 주입된 도구 호출 식별자
    """
    summary_lines = [f"- [{item['status']}] {item['content']}" for item in todos]
    summary_text = "TODO 목록이 업데이트되었습니다:\n" + "\n".join(summary_lines)

    logger.info(f"[TODO] 업데이트\n{chr(10).join(summary_lines)}")

    return Command(
        update={
            "todos": todos,
            "messages": [ToolMessage(summary_text, tool_call_id=tool_call_id)],
        }
    )


@tool(description="현재 TODO 목록을 조회합니다. 진행 중인 작업 목록과 각 항목의 상태를 확인합니다.")
def read_todos(state: Annotated[DeepAgentState, InjectedState]) -> str:
    """현재 TODO 목록을 조회합니다."""
    todos = state.get("todos", [])

    if not todos:
        return "현재 TODO 목록이 비어 있습니다."

    summary_lines = [f"- [{item['status']}] {item['content']}" for item in todos]
    return "현재 TODO 목록:\n" + "\n".join(summary_lines)
