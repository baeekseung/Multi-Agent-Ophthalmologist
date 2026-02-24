from typing import Annotated

from langchain.agents import create_agent
from langchain_core.tools import InjectedToolCallId, tool
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from langgraph.graph import END

from app.state import MainState
from app.prompts import GENERATE_FINAL_REPORT_PROMPT
from app.database.connection import SessionLocal
from app.database.models import PatientRecord


@tool
def save_patient_record(
    patient_name: str,
    patient_age: int,
    patient_gender: str,
    final_report: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """환자 진료 기록을 PostgreSQL 데이터베이스에 저장한다.

    Args:
        patient_name: 환자 이름
        patient_age: 환자 나이 (정수)
        patient_gender: 환자 성별 ('남성' 또는 '여성')
        final_report: 방금 생성한 최종 예비 진단서 전체 내용
    """
    print(f"[TOOL CALL]: save_patient_record called (환자: {patient_name})")
    consultation_summary = state.get("consultation_summary", "")
    try:
        with SessionLocal() as session:
            record = PatientRecord(
                patient_name=patient_name,
                patient_age=patient_age,
                patient_gender=patient_gender,
                consultation_summary=consultation_summary,
                final_report=final_report,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            record_id = record.id

        print(f"[TOOL CALL]: 진료기록 저장 완료. DB id: {record_id}")
        return Command(update={
            "messages": [
                ToolMessage(content=f"진료기록 저장 완료. DB id: {record_id}", tool_call_id=tool_call_id),
                SystemMessage(content="진료기록 저장이 완료되었습니다.", name="system"),
            ]
        })
    except Exception as e:
        print(f"[TOOL CALL ERROR]: 진료기록 저장 실패: {e}")
        return Command(update={
            "messages": [ToolMessage(content=f"저장 실패: {e}", tool_call_id=tool_call_id)]
        })


generate_final_report_agent = create_agent(
    model=ChatOpenAI(model="gpt-4o", temperature=0),
    tools=[save_patient_record],
    system_prompt=GENERATE_FINAL_REPORT_PROMPT,
    state_schema=MainState,
)


async def generate_final_report_node(state: MainState) -> Command:
    """상담이 충분히 완료된 경우 최종 예비 진단서를 생성하고 PostgreSQL에 저장한 후 그래프를 종료한다."""
    print("[AGENT CALLED]: generate_final_report called")

    consultation_summary = state.get("consultation_summary", "")
    mid_term_diagnosis_summary = state.get("mid_term_diagnosis_summary", "")

    response = await generate_final_report_agent.ainvoke({
        "messages": [HumanMessage(content=(
            f"## consultation_summary:\n{consultation_summary}\n\n"
            f"## expert_diagnosis_summary:\n{mid_term_diagnosis_summary}"
        ))],
        "consultation_summary": consultation_summary,  # InjectedState 주입 소스
    })

    # 에이전트 메시지에서 final_report 추출 (마지막 AIMessage)
    final_report_content = ""
    for m in reversed(response.get("messages", [])):
        if isinstance(m, AIMessage) and m.content:
            final_report_content = m.content
            break

    print(f"## GENERATE_FINAL_REPORT: Report generated:\n{final_report_content}\n")

    return Command(update={"final_report": final_report_content}, goto=END)
