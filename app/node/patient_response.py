from langchain_core.messages import HumanMessage
from langgraph.types import interrupt, Command
from app.state import MainState
from app.utils.logger import get_logger

logger = get_logger(__name__)

async def patient_response_node(state: MainState) -> Command:
    logger.info("[NODE] patient_response 시작")
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None   # 마지막 메시지(AI Message) 가져오기

    # Null 안전성 체크
    if last_message and hasattr(last_message, "content"):
        prompt_message = f"Doctor: {last_message.content}\nYour answer:"
    else:
        prompt_message = "이전 대화 내역이 없습니다. 시스템을 다시 시작해주세요."

    # interrupt를 통한 사용자 입력 대기
    # 그래프 실행이 일시 중지되고 외부(API)에서 Command(resume=...) 를 받을 때까지 대기
    user_input = interrupt({"question": last_message.content if last_message else prompt_message})

    # API에서 dict 형태로 넘어올 수 있음 (예: {"answer": "..."})
    if isinstance(user_input, dict):
        user_input = user_input.get("answer", str(user_input))

    human_message = HumanMessage(content=user_input.strip(), name="patient")
    logger.info(f"[NODE] patient_response 수신: {user_input.strip()[:100]}")
    logger.info("[NODE] patient_response 완료 → consultation_agent")
    return Command(goto='consultation_agent', update={'messages': [human_message]})