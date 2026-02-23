from langchain_core.messages import HumanMessage
from langgraph.types import interrupt, Command
from app.state import MainState

async def patient_response_node(state: MainState) -> Command:
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None   # 마지막 메시지(AI Message) 가져오기

    # Null 안전성 체크
    if last_message and hasattr(last_message, "content"):
        prompt_message = f"Doctor: {last_message.content}\nYour answer:"
    else:
        prompt_message = "이전 대화 내역이 없습니다. 시스템을 다시 시작해주세요."

    # interrupt를 통한 사용자 입력 대기
    # 그래프 실행이 일시 중지되고 외부에서 입력을 받을 때까지 대기
    # user_input = interrupt(prompt_message)
    
    while True:
        user_input = input(prompt_message)
        if user_input and user_input.strip():
            break
        print("빈 입력은 허용되지 않습니다. 다시 입력해주세요.")

    # 입력 받은 값으로 HumanMessage 생성
    human_message = HumanMessage(content=user_input.strip(), name="patient")
    print("\n")
    return Command(goto='consultation_agent', update={'messages': [human_message]})