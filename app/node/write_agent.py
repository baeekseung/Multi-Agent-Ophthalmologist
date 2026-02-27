from dotenv import load_dotenv
load_dotenv()

import os
from datetime import datetime

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import Annotated

from app.state import DeepAgentState
from app.utils.logger import get_logger
from app.prompts import WRITE_AGENT_INSTRUCTIONS

logger = get_logger(__name__)


@tool(parse_docstring=True)
def draft_section_tool(section_name: str, draft_content: str) -> str:
    """보고서 각 섹션의 초안을 작성하고 기록합니다.

    각 섹션 작성 전에 반드시 사용하여 구조적 사고를 기록합니다.

    Args:
        section_name: 작성할 섹션 이름
          (patient_summary | gap_analysis | guideline_review |
           diagnosis_recommendation | additional_tests)
        draft_content: 해당 섹션의 초안 내용

    Returns:
        초안이 기록되었음을 확인하는 메시지
    """
    logger.debug(f"[TOOL] draft_section_tool: [{section_name}] ({len(draft_content)}자)")
    return f"Draft recorded for [{section_name}]: {draft_content}"


@tool(parse_docstring=True)
def submit_report(
    patient_summary: str,
    gap_analysis: str,
    guideline_review: str,
    diagnosis_recommendation: str,
    additional_tests: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """완성된 안과 진단 보고서를 MD 파일로 저장하고 반환합니다.

    Args:
        patient_summary: 환자 개요 - 상담 요약에서 추출한 핵심 환자 정보
        gap_analysis: 진단 공백 분석 - gap_check_result.md 기반 내용
        guideline_review: 임상 가이드라인 검토 - guideline_retrieval_result.md 기반 내용
        diagnosis_recommendation: 의료 근거 기반 진단 권고 - 종합적 진단 의견 및 감별 진단
        additional_tests: 추가 검사 권고사항 - 확진을 위한 권고 검사 목록
        tool_call_id: 주입된 도구 호출 식별자

    Returns:
        diagnosis_report.md를 files에 저장하고 ToolMessage로 반환하는 Command
    """
    report_md = f"""# 안과 진단 연구 보고서

## 1. 환자 개요
{patient_summary}

## 2. 진단 공백 분석 (Gap Check)
{gap_analysis}

## 3. 임상 가이드라인 검토 (Guideline Review)
{guideline_review}

## 4. 의료 근거 기반 진단 권고
{diagnosis_recommendation}

## 5. 추가 검사 권고사항
{additional_tests}
"""
    logger.info(f"[TOOL] submit_report: diagnosis_report.md 저장 ({len(report_md)}자)")

    return Command(
        update={
            "files": {"diagnosis_report.md": report_md},
            "messages": [ToolMessage(report_md, tool_call_id=tool_call_id)],
        }
    )


@tool()
def save_report_file(
    state: Annotated[DeepAgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """로컬 파일시스템에 완성된 진단 보고서를 .md 파일로 저장합니다.

    submit_report 도구 호출 후 반드시 이 도구를 호출하여
    보고서를 실제 파일로 저장하세요.
    """
    content = state.get("files", {}).get("diagnosis_report.md", "")
    if not content:
        # submit_report가 먼저 호출되지 않은 경우
        logger.warning("[TOOL] save_report_file: diagnosis_report.md가 아직 없습니다. submit_report를 먼저 호출하세요.")
        return Command(
            update={"messages": [ToolMessage(
                "오류: diagnosis_report.md가 존재하지 않습니다. submit_report를 먼저 호출한 후 이 도구를 사용하세요.",
                tool_call_id=tool_call_id,
            )]}
        )

    save_dir = "reports"
    os.makedirs(save_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"{save_dir}/diagnosis_report_{timestamp}.md"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"[TOOL] save_report_file: 보고서 저장 완료 → {file_path} ({len(content)}자)")
    return Command(
        update={"messages": [ToolMessage(
            f"보고서가 저장되었습니다: {file_path}",
            tool_call_id=tool_call_id,
        )]}
    )


model = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

# read_collected_files는 analysis_agent_tools에 이미 포함되어 tools_by_name에서 참조됨
# write_agent_tools에는 write_agent 전용 도구만 포함
write_agent_tools = [draft_section_tool, submit_report, save_report_file]

write_agent = {
    "name": "write-agent",
    "description": "gap_check와 guideline_retrieval sub-task가 완료된 후, 누적된 연구 파일들을 종합하여 실제 전문의들이 임상에서 활용할 수 있는 최종 안과 진단 보고서(diagnosis_report.md)를 작성합니다. report_writing TODO에서만 호출하세요.",
    "prompt": WRITE_AGENT_INSTRUCTIONS,
    "tools": ["read_collected_files", "draft_section_tool", "submit_report", "save_report_file"],
    # "read_collected_files"는 analysis_agent_tools에서 이미 tools_by_name에 등록됨
}
