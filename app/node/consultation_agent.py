from dotenv import load_dotenv
load_dotenv()

from typing import Annotated, Literal

from app.prompts import UPDATE_QUESTIONS_TOOL_DESCRIPTION, CONSULTATION_AGENT_PROMPT
from app.state import Question, MainState
from app.database.connection import SessionLocal
from app.database.models import PatientRecord
from app.utils.messages_pretty_print import messages_pretty_print
from app.utils.logger import get_logger

from langchain.agents import create_agent
from langchain_core.tools import InjectedToolCallId, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langchain_openai import ChatOpenAI

logger = get_logger(__name__)

@tool(description=UPDATE_QUESTIONS_TOOL_DESCRIPTION, parse_docstring=True)
def update_questions(questions: list[Question], tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Create or update the agent's Question list for consultation planning and tracking.

    Args:
        questions: List of Question items with content and status
        tool_call_id: Tool call identifier for message response

    Returns:
        Command to update agent state with new Question list"""
    result = ""
    for i, question in enumerate(questions, 1):
        result += f"{i}. {question['content']} ({question['status']})\n"
    logger.debug(f"[TOOL] update_questions 호출\n{result.strip()}")

    all_completed = all(q["status"] == "completed" for q in questions)
    if all_completed:
        logger.info("[TOOL] update_questions - 모든 질문 완료")
        # 완료 마커를 ToolMessage content에 포함 (SystemMessage를 끼워넣으면
        # 두 도구가 동시 호출될 때 ToolMessage 사이에 role이 섞여 OpenAI 400 에러 발생)
        return Command(update={
            "messages": [ToolMessage(
                content=f"Updated question list to {questions}\n[STATUS: ALL_QUESTIONS_COMPLETED]",
                tool_call_id=tool_call_id,
            )]
        })
    else:
        return Command(update={
            "messages": [ToolMessage(content=f"Updated question list to {questions}", tool_call_id=tool_call_id)]})


@tool(parse_docstring=True)
def search_previous_records(
    patient_name: str,
    patient_age: int,
    patient_gender: Literal["남성", "여성"],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """환자의 이전 진료기록을 PostgreSQL에서 검색합니다.
    인적사항(이름, 나이, 성별) 수집 완료 후 반드시 호출하세요.

    Args:
        patient_name: 환자 이름
        patient_age: 환자 나이
        patient_gender: 환자 성별
    """
    logger.info(f"[TOOL] search_previous_records 호출 - {patient_name}, {patient_age}세, {patient_gender}")

    session = SessionLocal()
    try:
        records = session.query(PatientRecord).filter(
            PatientRecord.patient_name.ilike(f"%{patient_name}%"),
            PatientRecord.patient_age == patient_age,
            PatientRecord.patient_gender == patient_gender,
        ).order_by(PatientRecord.created_at.desc()).all()

        if not records:
            formatted_result = "이전 진료기록이 없습니다."
            logger.info(f"[TOOL] search_previous_records - 이전 기록 없음")
        else:
            formatted_result = f"## 이전 진료기록 ({len(records)}건)\n\n"
            for i, record in enumerate(records, 1):
                created_at = record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "날짜 미상"
                formatted_result += f"### 기록 {i} ({created_at})\n"
                formatted_result += f"**진료상담 요약:**\n{record.consultation_summary}\n\n"
                formatted_result += f"**최종 진단서:**\n{record.final_report}\n\n"
                formatted_result += "---\n\n"
            logger.info(f"[TOOL] search_previous_records - {len(records)}건 조회됨")
    except Exception as e:
        logger.error(f"[TOOL] search_previous_records 오류: {e}")
        formatted_result = "이전 진료기록 조회 중 오류가 발생했습니다."
    finally:
        session.close()

    return Command(update={
        "previous_records": formatted_result,
        "messages": [ToolMessage(content=formatted_result, tool_call_id=tool_call_id)],
    })


consultation_agent = create_agent(
    model=ChatOpenAI(model="gpt-4o-mini", temperature=0.1),
    tools=[update_questions, search_previous_records],
    system_prompt=CONSULTATION_AGENT_PROMPT,
    state_schema=MainState)

async def consultation_agent_node(state: MainState) -> Command:
    messages = state.get("messages", [])
    logger.info("[NODE] consultation_agent 시작")
    logger.debug(f"[NODE] 현재 메시지 수: {len(messages)}\n{messages_pretty_print(messages)}")

    response = await consultation_agent.ainvoke({"messages": messages})

    # ToolMessage의 완료 마커로 완료 여부 확인
    # (SystemMessage를 messages에 삽입하면 동시 tool call 시 OpenAI 400 에러 발생)
    completion_triggered = any(
        isinstance(m, ToolMessage) and "ALL_QUESTIONS_COMPLETED" in str(m.content)
        for m in response.get("messages", [])
    )

    next_node = "summarize_consultation" if completion_triggered else "patient_response"
    logger.info(f"[NODE] consultation_agent 완료 → {next_node}")

    if completion_triggered:
        return Command(goto="summarize_consultation", update=response)
    else:
        return Command(goto="patient_response", update=response)