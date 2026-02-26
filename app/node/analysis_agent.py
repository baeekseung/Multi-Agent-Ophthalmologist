from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated, Literal

from app.state import DeepAgentState
from app.utils.logger import get_logger
from app.prompts import ANALYSIS_AGENT_INSTRUCTIONS

logger = get_logger(__name__)


@tool(description="가상 파일 시스템에서 수집된 모든 연구 파일의 목록과 내용을 반환합니다. 파일이 없으면 task description에 포함된 검색 결과를 분석하세요.")
def read_collected_files(
    state: Annotated[DeepAgentState, InjectedState],
) -> str:
    files = state.get("files", {})
    if not files:
        return "수집된 파일이 없습니다. task description에 포함된 검색 결과를 분석하세요."
    result_parts = [f"총 {len(files)}개 파일:\n"]
    for filename, content in files.items():
        result_parts.append(f"=== [{filename}] ===\n{content}\n")
    return "\n".join(result_parts)


@tool(parse_docstring=True)
def analyze_tool(analysis: str) -> str:
    """수집된 정보의 충분성을 분석하고 판단 근거를 기록합니다.

    각 분석 단계에서 반드시 사용하여 구조적 사고를 기록합니다.

    Args:
        analysis: 현재 TODO 요구사항 vs 수집 정보 비교 분석 내용

    Returns:
        분석 내용이 기록되었음을 확인하는 메시지
    """
    logger.debug(f"[TOOL] analyze_tool 분석 기록: {analysis[:200]}{'...' if len(analysis) > 200 else ''}")
    return f"Analysis recorded: {analysis}"


@tool(parse_docstring=True)
def submit_analysis_result(
    sufficiency: Literal["SUFFICIENT", "INSUFFICIENT"],
    analysis_summary: str,
    missing_items: list[str],
    recommendations: list[str],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """충분성 분석 결과를 구조화된 형식으로 제출합니다.

    Args:
        sufficiency: 충분성 판정 - "SUFFICIENT" 또는 "INSUFFICIENT"
        analysis_summary: 수집된 정보에 대한 전반적 평가 요약
        missing_items: 부족한 정보 항목 목록 (충분한 경우 빈 리스트)
        recommendations: 추가 검색 쿼리 또는 작업 권고사항 목록

    Returns:
        분석 결과를 ToolMessage로 반환하는 Command
    """
    result_text = f"""## 충분성 분석 결과

**판정**: {sufficiency}

**분석 요약**: {analysis_summary}"""
    if missing_items:
        result_text += "\n\n**부족한 정보**:\n" + "\n".join(f"- {item}" for item in missing_items)
    if recommendations:
        result_text += "\n\n**권고 사항**:\n" + "\n".join(f"- {rec}" for rec in recommendations)

    logger.info(f"[TOOL] submit_analysis_result: {sufficiency} | {analysis_summary[:100]}{'...' if len(analysis_summary) > 100 else ''}")
    if missing_items:
        logger.debug(f"부족한 항목: {missing_items}")

    return Command(
        update={"messages": [ToolMessage(result_text, tool_call_id=tool_call_id)]}
    )


model = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

analysis_agent_tools = [read_collected_files, analyze_tool, submit_analysis_result]

analysis_agent = {
    "name": "information-analysis-agent",
    "description": "수집된 의료 연구 정보가 현재 진행 중인 TODO 작업을 완료하기에 충분한지 분석합니다. deep_search_agent 검색 후 충분성 확인이 필요할 때 호출하세요.",
    "prompt": ANALYSIS_AGENT_INSTRUCTIONS,
    "tools": ["read_collected_files", "analyze_tool", "submit_analysis_result"],
}
