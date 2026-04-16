import asyncio
from datetime import datetime

from app.utils.logger import setup_logging

# thread id로 사용
def get_current_datetime_str() -> str:
    return datetime.now().strftime("%Y_%m_%d %H:%M:%S")


async def main(thread_id: str):
    setup_logging(thread_id)

    from app.graph import build_graph
    from langchain_core.messages import HumanMessage
    from langgraph.types import Command
    from app.prompts import INITIAL_CONSULTATION_MESSAGE

    graph = await build_graph()

    config = {"configurable": {"thread_id": thread_id}}

    consultation_summary = "No history"
    messages = [HumanMessage(
        content=f"## expert_opinion: {INITIAL_CONSULTATION_MESSAGE}\n\n## previous_consultation_summary: {consultation_summary}",
        name="expert",
    )]

    current_input = {"messages": messages}

    # interrupt 루프: patient_response_node의 interrupt()를 CLI에서 처리
    while True:
        interrupted = False
        question_text = None

        async for chunk in graph.astream(current_input, config=config, stream_mode="updates"):
            if "__interrupt__" in chunk:
                interrupt_value = chunk["__interrupt__"][0].value
                question_text = interrupt_value.get("question", "")
                interrupted = True
                break

        if not interrupted:
            print("\n[진료 프로세스 완료]")
            break

        # 질문 출력 및 사용자 입력 수신
        print(f"\n{question_text}")
        loop = asyncio.get_event_loop()
        user_answer = await loop.run_in_executor(None, lambda: input("환자: ").strip())

        current_input = Command(resume={"answer": user_answer})


if __name__ == "__main__":
    asyncio.run(main(thread_id=get_current_datetime_str()))
