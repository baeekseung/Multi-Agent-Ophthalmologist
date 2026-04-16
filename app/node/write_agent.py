import os
from datetime import datetime

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
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


@tool(parse_docstring=True)
def save_report_file(
    patient_name: str,
    patient_age: int,
    patient_gender: str,
    state: Annotated[DeepAgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """로컬 파일시스템에 완성된 진단 보고서를 .md 파일로 저장하고 PostgreSQL에 환자 기록을 저장합니다.

    submit_report 도구 호출 후 반드시 이 도구를 호출하여
    보고서를 실제 파일로 저장하세요.
    보고서의 "환자 개요" 섹션에서 환자 인적정보를 파싱하여 전달해야 합니다.

    Args:
        patient_name: 환자 이름 (보고서 환자 개요에서 파싱)
        patient_age: 환자 나이 (보고서 환자 개요에서 파싱)
        patient_gender: 환자 성별 (보고서 환자 개요에서 파싱, 예: 남성/여성)

    Returns:
        로컬 파일 저장 및 DB 저장 결과를 반환하는 Command
    """
    content = state.get("files", {}).get("diagnosis_report.md", "")
    if not content:
        logger.warning("[TOOL] save_report_file: diagnosis_report.md가 아직 없습니다. submit_report를 먼저 호출하세요.")
        return Command(
            update={"messages": [ToolMessage(
                "오류: diagnosis_report.md가 존재하지 않습니다. submit_report를 먼저 호출한 후 이 도구를 사용하세요.",
                tool_call_id=tool_call_id,
            )]}
        )

    # 1. 로컬 파일 저장
    save_dir = "reports"
    os.makedirs(save_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"{save_dir}/diagnosis_report_{timestamp}.md"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"[TOOL] save_report_file: 보고서 저장 완료 → {file_path} ({len(content)}자)")

    # 2. PostgreSQL PatientRecord 저장
    consultation_summary = state.get("files", {}).get("consultation_summary.txt", "")
    if not consultation_summary:
        consultation_summary = "상담 요약 정보 없음"
        logger.warning("[TOOL] save_report_file: consultation_summary.txt가 files에 없습니다.")

    try:
        from app.database.connection import SessionLocal
        from app.database.models import PatientRecord

        db = SessionLocal()
        record = PatientRecord(
            patient_name=patient_name,
            patient_age=patient_age,
            patient_gender=patient_gender,
            consultation_summary=consultation_summary,
            final_report=content,
        )
        db.add(record)
        db.commit()
        record_id = record.id
        db.close()

        logger.info(f"[TOOL] save_report_file: DB 저장 완료 → PatientRecord(id={record_id})")
        db_msg = f", DB 저장 완료 (PatientRecord id={record_id})"

        # 벡터 DB에 환자 증례 임베딩 저장 (유사 증례 검색을 위해)
        try:
            from app.tools.patient_similarity import add_patient_case
            add_patient_case(
                record_id=record_id,
                patient_name=patient_name,
                patient_age=patient_age,
                patient_gender=patient_gender,
                consultation_summary=consultation_summary,
                final_report=content,
            )
        except Exception as vec_err:
            logger.warning(f"[TOOL] save_report_file: 벡터 임베딩 저장 실패 (DB 저장은 성공) → {vec_err}")

    except Exception as e:
        logger.error(f"[TOOL] save_report_file: DB 저장 실패 → {e}")
        db_msg = f", DB 저장 실패: {e}"

    return Command(
        update={"messages": [ToolMessage(
            f"보고서가 저장되었습니다: {file_path}{db_msg}",
            tool_call_id=tool_call_id,
        )]}
    )


write_agent_tools = [draft_section_tool, submit_report, save_report_file]

write_agent = {
    "name": "write-agent",
    "description": "gap_check와 guideline_retrieval sub-task가 완료된 후, 누적된 연구 파일들을 종합하여 실제 전문의들이 임상에서 활용할 수 있는 최종 안과 진단 보고서(diagnosis_report.md)를 작성합니다. report_writing TODO에서만 호출하세요.",
    "prompt": WRITE_AGENT_INSTRUCTIONS,
    "tools": ["read_collected_files", "draft_section_tool", "submit_report", "save_report_file"],
    # "read_collected_files"는 analysis_agent_tools에서 이미 tools_by_name에 등록됨
}
