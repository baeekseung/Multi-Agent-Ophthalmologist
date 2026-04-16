from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command
from typing_extensions import Annotated

from app.utils.logger import get_logger
from app.prompts import ORGANIZE_AGENT_INSTRUCTIONS

logger = get_logger(__name__)


@tool(parse_docstring=True)
def synthesize_tool(synthesis: str) -> str:
    """수집된 정보를 종합하고 정리하는 과정을 기록합니다.

    각 정리 단계에서 반드시 사용하여 구조적 사고를 기록합니다.

    Args:
        synthesis: 핵심 정보 추출 및 정리 방향에 대한 상세 분석 내용

    Returns:
        합성 과정이 기록되었음을 확인하는 메시지
    """
    logger.debug(f"[TOOL] synthesize_tool 합성 기록: {synthesis[:200]}{'...' if len(synthesis) > 200 else ''}")
    return f"Synthesis recorded: {synthesis}"


@tool(parse_docstring=True)
def submit_organized_result(
    task_name: str,
    result_summary: str,
    key_findings: list[str],
    clinical_implications: list[str],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """sub-task 수행 결과를 종합하여 구조화된 형식으로 저장하고 반환합니다.

    Args:
        task_name: 현재 sub-task 이름 (예: gap_check, guideline_retrieval)
        result_summary: sub-task 수행 결과에 대한 종합 요약 (1-3문장)
        key_findings: 진단에 직접 활용 가능한 핵심 발견 사항 목록 (3-7개)
        clinical_implications: 환자 케이스에 적용할 임상적 시사점 목록 (2-5개)
        tool_call_id: 주입된 도구 호출 식별자

    Returns:
        정리된 결과를 파일로 저장하고 ToolMessage로 반환하는 Command
    """
    result_text = f"## {task_name} 수행 결과 정리\n\n**요약**: {result_summary}"
    if key_findings:
        result_text += "\n\n**핵심 발견 사항**:\n" + "\n".join(f"- {f}" for f in key_findings)
    if clinical_implications:
        result_text += "\n\n**임상적 시사점**:\n" + "\n".join(f"- {c}" for c in clinical_implications)

    filename = f"{task_name}_result.md"

    logger.info(f"[TOOL] submit_organized_result: '{filename}' 저장 | 요약: {result_summary[:100]}{'...' if len(result_summary) > 100 else ''}")
    logger.debug(f"핵심 발견 사항: {key_findings}")

    return Command(
        update={
            "files": {filename: result_text},
            "messages": [ToolMessage(result_text, tool_call_id=tool_call_id)],
        }
    )


organize_agent_tools = [synthesize_tool, submit_organized_result]

organize_agent = {
    "name": "organize-agent",
    "description": "analysis_agent가 SUFFICIENT 판정을 내린 후, 수집된 모든 정보를 종합하여 현재 sub-task의 수행 결과를 구조화된 형식으로 정리하고 파일로 저장합니다. 각 sub-task의 마지막 단계(SUFFICIENT 판정 직후)에 호출하세요.",
    "prompt": ORGANIZE_AGENT_INSTRUCTIONS,
    "tools": ["read_collected_files", "synthesize_tool", "submit_organized_result"],
    # "read_collected_files"는 analysis_agent_tools에서 이미 tools_by_name에 등록됨
}
