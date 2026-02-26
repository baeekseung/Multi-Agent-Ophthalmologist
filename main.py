import asyncio
from app.graph import build_graph
from langchain_core.messages import HumanMessage

from app.prompts import INITIAL_CONSULTATION_MESSAGE

async def main(thread_id: str):
    graph = await build_graph()
    
    # 그래프 실행
    config = {
    'configurable': {
        'thread_id': thread_id
    }}

    consultation_summary = "아직 진료상담 이력이 없습니다."
    mid_term_diagnosis_result = INITIAL_CONSULTATION_MESSAGE
    messages = [HumanMessage(content=f"## previous_consultation_summary: {consultation_summary}\n\n## expert_opinion: {mid_term_diagnosis_result}", name="expert")]
    result = await graph.ainvoke({"messages": messages}, config=config)

if __name__ == "__main__":
    asyncio.run(main(thread_id='thread2'))

"""29살 남자 백승주입니다. 어제부터 왼쪽 눈이 따가웠고, 특히 눈을 뜨고 있을때 더욱 그렇습니다. 과거력이나 전신질환은 없습니다."""