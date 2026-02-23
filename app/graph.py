from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.state import MainState
from app.node.patient_response import patient_response_node
from app.node.consultation_agent import consultation_agent_node
from app.node.summarize_consultation import summarize_consultation_node
from app.node.mid_level_analysis import (
    supervisor_agent_node,
    expert1_agent,
    expert2_agent,
    expert3_agent,
    evaluate_consensus_agent,
    summarize_consensus_agent,
)

async def build_graph():
    workflow = StateGraph(MainState)

    workflow.add_node("patient_response", patient_response_node)
    workflow.add_node("consultation_agent", consultation_agent_node)
    workflow.add_node("summarize_consultation", summarize_consultation_node)

    # mid_level_analysis
    workflow.add_node("supervisor", supervisor_agent_node)
    workflow.add_node("expert1", expert1_agent)
    workflow.add_node("expert2", expert2_agent)
    workflow.add_node("expert3", expert3_agent)
    workflow.add_node("evaluate_consensus_agent", evaluate_consensus_agent)
    workflow.add_node("summarize_consensus_agent", summarize_consensus_agent)

    workflow.set_entry_point("consultation_agent")

    graph = workflow.compile(checkpointer=MemorySaver())
    return graph
