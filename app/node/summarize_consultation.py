from langgraph.types import Command
from langchain_openai import ChatOpenAI

from app.state import MainState
from langchain_core.messages import RemoveMessage, HumanMessage
from app.prompts import INITIAL_SUMMARIZE_MESSAGES_PROMPT, UPDATE_SUMMARIZE_MESSAGES_PROMPT
from app.utils.logger import get_logger

logger = get_logger(__name__)

async def summarize_consultation_node(state: MainState) -> Command:
    messages = state.get("messages", [])
    consultation_summary = state.get("consultation_summary", "")
    consultation_turn = state.get("consultation_turn", 1)

    logger.info(f"[NODE] summarize_consultation 시작 (턴 {consultation_turn}, 메시지 {len(messages)}건)")

    if consultation_summary != "":
        summary_prompt = UPDATE_SUMMARIZE_MESSAGES_PROMPT.format(previous_summary=consultation_summary, messages=messages)
    else:
        summary_prompt = INITIAL_SUMMARIZE_MESSAGES_PROMPT.format(messages=messages)

    summary_model = ChatOpenAI(model="gpt-4o", temperature=0.1)
    new_summary = await summary_model.ainvoke(summary_prompt)

    # 이전 진료기록이 존재하면 요약본에 병합
    previous_records = state.get("previous_records", "")
    summary_content = new_summary.content
    if previous_records and previous_records != "이전 진료기록이 없습니다.":
        summary_content += f"\n\n---\n## 이전 진료기록 참고\n{previous_records}"

    logger.info(f"[NODE] summarize_consultation 완료 (턴 {consultation_turn}) → supervisor")
    logger.debug(f"상담 요약본:\n{summary_content}")

    # 전체 상담 내용의 요약본으로 상담내역을 저장, 단기 메모리 초기화
    return Command(goto='supervisor', update={'consultation_summary': summary_content, 'messages': [RemoveMessage(id=m.id) for m in messages], 'supervisor_messages': [HumanMessage(content=f"{consultation_turn}번째 상담 요약본: {summary_content}", name="summarize_consultation")]} )