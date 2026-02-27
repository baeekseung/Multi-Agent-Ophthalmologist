from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from app.database.connection import init_db
from langgraph.graph import END

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
from app.node.diagnosis_agent import diagnosis_agent_node
from app.utils.logger import get_logger

logger = get_logger(__name__)

async def build_graph():
    logger.info("[GRAPH] 그래프 빌드 시작")
    init_db()
    logger.info("[GRAPH] DB 초기화 완료")
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

    workflow.add_node("diagnosis_agent", diagnosis_agent_node)

    workflow.set_entry_point("consultation_agent")

    graph = workflow.compile(checkpointer=MemorySaver())
    logger.info("[GRAPH] 그래프 빌드 완료 (노드 수: %d)", len(workflow.nodes))
    return graph
