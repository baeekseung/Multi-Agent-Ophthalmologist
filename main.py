import asyncio
from app.utils.logger import setup_logging


async def main(thread_id: str):
    # app 모듈 import 전에 로그 파일을 thread_id 기반으로 전환
    setup_logging(thread_id)

    from app.graph import build_graph
    from langchain_core.messages import HumanMessage
    from app.prompts import INITIAL_CONSULTATION_MESSAGE

    graph = await build_graph()

    # 그래프 실행
    config = {
        'configurable': {
            'thread_id': thread_id
        }
    }

    consultation_summary = "아직 진료상담 이력이 없습니다."
    mid_term_diagnosis_result = INITIAL_CONSULTATION_MESSAGE
    messages = [HumanMessage(content=f"## previous_consultation_summary: {consultation_summary}\n\n## expert_opinion: {mid_term_diagnosis_result}", name="expert")]
    result = await graph.ainvoke({"messages": messages}, config=config)

if __name__ == "__main__":
    def get_current_datetime_str():
        """현재 날짜와 시간을 'YYYY-MM-DD HH:MM:SS' 형식의 문자열로 반환합니다."""
        from datetime import datetime
        return datetime.now().strftime("%Y_%m_%d %H:%M:%S")
    

    asyncio.run(main(thread_id=get_current_datetime_str()))

"""29살 남자 백승주입니다. 어제부터 왼쪽 눈이 따가웠고, 특히 눈을 뜨고 있을때 더욱 그렇습니다. 과거력이나 전신질환은 없습니다."""
