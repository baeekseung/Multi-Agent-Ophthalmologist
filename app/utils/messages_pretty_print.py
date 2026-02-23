# agent의 state:messages를 예쁘게 출력하는 함수
from langchain_core.messages import AnyMessage
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

def messages_pretty_print(messages: list[AnyMessage]) -> str:
    result = "----------------------------------------\n"
    for message in messages:
        msg_name = getattr(message, "name", None)
        name_str = f" ({msg_name})" if msg_name else ""
        if message.type == "ai" and (message.content is None or message.content == ""):
            # Tool call made by AI
            # Try to show tool call details if possible
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                # tool_calls is typically a list of dicts, try to format them
                tc_strings = []
                for tc in tool_calls:
                    tc_name = tc.get("name", "unknown")
                    args = tc.get("args", {})
                    tc_strings.append(f"{tc_name}({args})")
                tool_call_info = "; ".join(tc_strings)
            else:
                tool_call_info = "Tool call issued, but details not available"
            result += f"[{message.type.upper()}]{name_str} [TOOL CALL] {tool_call_info}\n\n"
        else:
            result += f"[{message.type.upper()}]{name_str} {message.content}\n\n"
    result += "----------------------------------------\n"
    return result.strip()

if __name__ == "__main__":
    messages = [
        HumanMessage(content="Hello, how are you?", name="patient"),
        AIMessage(content="I'm fine, thank you!", name="doctor"),
        AIMessage(content="", tool_calls=[{"name": "update_questions", "id": "123","args": {"questions": [{"content": "What is your name?", "status": "pending"}]}}]),
        ToolMessage(content="I'm a tool message!", tool_call_id="123", name="update_questions"),
    ]
    print(messages_pretty_print(messages))