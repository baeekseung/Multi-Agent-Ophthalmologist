from langgraph.types import Command
from langchain_openai import ChatOpenAI

from app.state import MainState
from langchain_core.messages import RemoveMessage
from app.prompts import INITIAL_SUMMARIZE_MESSAGES_PROMPT, UPDATE_SUMMARIZE_MESSAGES_PROMPT

async def summarize_consultation_node(state: MainState) -> Command:
    print(f"[TOOL CALL]: summarize_consultation called")
    messages = state.get("messages", [])
    consultation_summary = state.get("consultation_summary", "")

    if consultation_summary != "":
        summary_prompt = UPDATE_SUMMARIZE_MESSAGES_PROMPT.format(previous_summary=consultation_summary, messages=messages)
    else:
        summary_prompt = INITIAL_SUMMARIZE_MESSAGES_PROMPT.format(messages=messages)

    summary_model = ChatOpenAI(model="gpt-4o", temperature=0.1)
    new_summary = await summary_model.ainvoke(summary_prompt)
    print(f"summary: {new_summary.content}\n")

    # 전체 상담 내용의 요약본으로 상담내역을 저장, 단기 메모리 초기화
    return Command(goto='supervisor', update={'consultation_summary': new_summary.content, 'messages': [RemoveMessage(id=m.id) for m in state.get("messages", [])]})