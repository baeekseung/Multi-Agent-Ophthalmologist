from langgraph.types import Command
from langgraph.graph import END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from app.state import MainState
from app.prompts import GENERATE_FINAL_REPORT_PROMPT


async def generate_final_report_node(state: MainState) -> Command:
    """상담이 충분히 완료된 경우 최종 예비 진단서를 생성하고 그래프를 종료한다."""
    print("[AGENT CALLED]: generate_final_report called")

    consultation_summary = state.get("consultation_summary", "")
    mid_term_diagnosis_summary = state.get("mid_term_diagnosis_summary", "")

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", GENERATE_FINAL_REPORT_PROMPT),
        ("user",
         "## consultation_summary:\n{consultation_summary}\n\n"
         "## expert_diagnosis_summary:\n{expert_diagnosis_summary}")
    ])
    chain = prompt | llm
    response = await chain.ainvoke({
        "consultation_summary": consultation_summary,
        "expert_diagnosis_summary": mid_term_diagnosis_summary,
    })

    print(f"## GENERATE_FINAL_REPORT: Report generated:\n{response.content}\n")

    return Command(
        update={"final_report": response.content},
        goto=END,
    )
