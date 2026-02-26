from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from typing_extensions import Annotated

from app.prompts import WRITE_AGENT_INSTRUCTIONS


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
    return Command(
        update={
            "files": {"diagnosis_report.md": report_md},
            "messages": [ToolMessage(report_md, tool_call_id=tool_call_id)],
        }
    )


model = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

# read_collected_files는 analysis_agent_tools에 이미 포함되어 tools_by_name에서 참조됨
# write_agent_tools에는 write_agent 전용 도구만 포함
write_agent_tools = [draft_section_tool, submit_report]

write_agent = {
    "name": "write-agent",
    "description": "gap_check와 guideline_retrieval sub-task가 완료된 후, 누적된 연구 파일들을 종합하여 실제 전문의들이 임상에서 활용할 수 있는 최종 안과 진단 보고서(diagnosis_report.md)를 작성합니다. report_writing TODO에서만 호출하세요.",
    "prompt": WRITE_AGENT_INSTRUCTIONS,
    "tools": ["read_collected_files", "draft_section_tool", "submit_report"],
    # "read_collected_files"는 analysis_agent_tools에서 이미 tools_by_name에 등록됨
}
