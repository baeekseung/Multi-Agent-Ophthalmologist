from dotenv import load_dotenv
load_dotenv()
from typing import Annotated

from app.prompts import UPDATE_QUESTIONS_TOOL_DESCRIPTION, CONSULTATION_AGENT_PROMPT
from app.state import Question, MainState
from app.utils.messages_pretty_print import messages_pretty_print

from langchain.agents import create_agent
from langchain_core.tools import InjectedToolCallId, tool
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage, SystemMessage
from langgraph.types import Command
from langchain_openai import ChatOpenAI

@tool(description=UPDATE_QUESTIONS_TOOL_DESCRIPTION, parse_docstring=True)
def update_questions(questions: list[Question], tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Create or update the agent's Question list for consultation planning and tracking.

    Args:
        questions: List of Question items with content and status
        tool_call_id: Tool call identifier for message response

    Returns:
        Command to update agent state with new Question list"""
    print(f"[TOOL CALL]: update_questions called")
    result = ""
    for i, question in enumerate(questions, 1):
        result += f"{i}. {question['content']} ({question['status']})\n"
    print(f"{result.strip()}\n")

    all_completed = all(q["status"] == "completed" for q in questions)
    if all_completed:
        print("모든 질문이 완료되었습니다.")
        return Command(update={
            "messages": [ToolMessage(content=f"Updated question list to {questions}", tool_call_id=tool_call_id), SystemMessage(content="모든 질문이 완료되었습니다.", name="expert")]})
    else:
        return Command(update={
            "messages": [ToolMessage(content=f"Updated question list to {questions}", tool_call_id=tool_call_id)]})


consultation_agent = create_agent(
    model=ChatOpenAI(model="gpt-4o", temperature=0.1),
    tools=[update_questions],
    system_prompt=CONSULTATION_AGENT_PROMPT,
    state_schema=MainState)

async def consultation_agent_node(state: MainState) -> Command:
    messages = state.get("messages", [])
    print(f"[AGENT CALLED]: consultation agent called")
    # print(messages_pretty_print(messages))
    response = await consultation_agent.ainvoke({"messages": messages})

    # print(response["messages"])
    # print(response["consultation_next"])

    # SystemMessage 기반으로 완료 여부 확인 (LLM이 consultation_next를 덮어쓸 수 있으므로)
    completion_triggered = any(
        isinstance(m, SystemMessage) and "모든 질문이 완료" in m.content
        for m in response.get("messages", [])
    )

    if completion_triggered:
        return Command(goto="summarize_consultation", update=response)
    else:
        return Command(goto="patient_response", update=response)
