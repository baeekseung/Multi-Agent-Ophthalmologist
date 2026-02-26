from dotenv import load_dotenv
load_dotenv()

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from langgraph.graph import END

from app.prompts import (
    DIAGNOSIS_AGENT_INSTRUCTIONS,
    DIAGNOSIS_AGENT_TODO_INSTRUCTIONS,
)
from app.state import DeepAgentState, MainState
from app.utils.subagent_calling_tool import _create_task_tool
from app.utils.todo_tools import read_todos, write_todos
from app.utils.logger import get_logger
from app.node.deep_search_agent import deep_search_agent, deep_search_agent_tools
from app.node.analysis_agent import analysis_agent, analysis_agent_tools
from app.node.organize_agent import organize_agent, organize_agent_tools
from app.node.write_agent import write_agent, write_agent_tools

logger = get_logger(__name__)


model = ChatOpenAI(model="gpt-4o", temperature=0.0)

# 네 서브에이전트의 도구를 합산하여 tools_by_name 룩업에 모두 등록
# organize_agent_tools, write_agent_tools에는 read_collected_files 미포함 (analysis_agent_tools에서 이미 제공)
sub_agent_tools = deep_search_agent_tools + analysis_agent_tools + organize_agent_tools + write_agent_tools
task_tool = _create_task_tool(sub_agent_tools, [deep_search_agent, analysis_agent, organize_agent, write_agent], model, DeepAgentState)

# 메인 에이전트 도구: TODO 관리 + 서브에이전트 위임
main_agent_tools = [write_todos, read_todos, task_tool]

# 메인 에이전트 생성
agent = create_agent(
    model,
    main_agent_tools,
    system_prompt=DIAGNOSIS_AGENT_INSTRUCTIONS.format(
        todo_instructions=DIAGNOSIS_AGENT_TODO_INSTRUCTIONS
    ),
    state_schema=DeepAgentState,
)


async def diagnosis_agent_node(state: MainState) -> Command:
    consultation_summary = state.get("consultation_summary", "")
    mid_term_summary = state.get("mid_term_diagnosis_summary", "")

    logger.info("[NODE] diagnosis_agent 시작 - 심층 진단 연구 수행")
    logger.debug(f"환자 상담 요약 ({len(consultation_summary)}자):\n{consultation_summary[:500]}{'...' if len(consultation_summary) > 500 else ''}")
    logger.debug(f"중간 전문의 소견 ({len(mid_term_summary)}자):\n{mid_term_summary[:300]}{'...' if len(mid_term_summary) > 300 else ''}")

    initial_message = f"""환자 상담 요약:
{consultation_summary}

중간 전문의 소견:
{mid_term_summary}

위 정보를 바탕으로 심층 진단 연구를 수행하고 최종 진단 연구 보고서를 작성하세요.
"""

    result = await agent.ainvoke({
        "messages": [HumanMessage(content=initial_message)],
    })

    final_report = result["messages"][-1].content
    saved_files = list(result.get("files", {}).keys())

    logger.info(f"[NODE] diagnosis_agent 완료 | 생성된 파일: {saved_files}")
    logger.debug(f"최종 보고서 ({len(final_report)}자):\n{final_report[:500]}{'...' if len(final_report) > 500 else ''}")

    return Command(
        update={"diagnosis_research_result": final_report},
        goto=END,
    )
