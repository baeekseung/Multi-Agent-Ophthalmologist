from tavily import TavilyClient

from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.tools import InjectedToolArg, InjectedToolCallId, tool
from langgraph.types import Command
from typing_extensions import Annotated, Literal

from app.utils.get_current_time import get_current_time
from app.utils.logger import get_logger
from app.prompts import SUMMARIZE_WEB_SEARCH_PROMPT, MEDICAL_RESEARCHER_INSTRUCTIONS
from app.tools.guideline_rag import guideline_search_tool

logger = get_logger(__name__)

tavily_client = TavilyClient()
def get_web_search(search_query: str, max_results: int = 2, topic: Literal["general", "news", "finance"] = "general", include_raw_content: bool = True) -> dict:
    result = tavily_client.search(
        search_query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )
    return result


class Summary(BaseModel):
    """Schema for webpage content summarization."""
    summary: str = Field(description="Key learnings from the webpage.")

summarization_model = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

def summarize_webpage_contents(search_query: str, webpage_contents: list[str]) -> list[Summary]:
    if not webpage_contents:
        return []

    structured_model = summarization_model.with_structured_output(Summary)

    batch_inputs = [[HumanMessage(content=SUMMARIZE_WEB_SEARCH_PROMPT.format(search_query=search_query, webpage_content=content, date=get_current_time()))] for content in webpage_contents]

    try:
        # batch() 메서드로 병렬 처리 실행
        summaries = structured_model.batch(batch_inputs)
        return summaries

    except Exception as e:
        # 실패시 기본 요약 객체 리스트 반환
        logger.warning(f"Batch 처리 실패, 순차 처리로 전환: {e}")
        return [
            Summary(
                summary=(content[:1000] + "..." if len(content) > 1000 else content),
            )
            for content in webpage_contents
        ]

def process_search_results(query: str, results: dict) -> list[dict]:
    search_results = results.get("results", [])

    if not search_results:
        return []

    # 모든 raw_content를 리스트로 추출 (batch 입력용)
    raw_contents = [result.get("raw_content", "") for result in search_results]

    # batch 방식으로 모든 콘텐츠를 병렬 요약 처리 (summarize_webpage_contents 함수 활용)
    summary_objects = summarize_webpage_contents(query, raw_contents)

    # 요약 결과와 원본 검색 결과를 결합하여 최종 결과 생성
    processed_results = []
    for result, summary_obj in zip(search_results, summary_objects):
        processed_results.append(
            {
                "url": result["url"],
                "title": result["title"],
                "summary": summary_obj.summary,
                # "raw_content": result.get("raw_content", ""),
            }
        )

    return processed_results

@tool(parse_docstring=True)
def tavily_search(query: str, tool_call_id: Annotated[str, InjectedToolCallId], max_results: Annotated[int, InjectedToolArg] = 2, topic: Annotated[Literal["general", "news", "finance"], InjectedToolArg] = "general") -> Command:
    """웹 검색을 수행하고 결과 요약을 반환합니다.
    웹 검색을 수행하여 에이전트가 다음 단계를 결정하는 데 필요한 정보를 반환합니다.

    Args:
        query: 실행할 검색 쿼리
        tool_call_id: 주입된 도구 호출 식별자
        max_results: 반환할 최대 결과 수 (기본값: 2)
        topic: 토픽 필터 - 'general', 'news', 또는 'finance' (기본값: 'general')

    Returns:
        검색 결과 요약을 제공하는 Command
    """
    logger.info(f"[TOOL] tavily_search: '{query}' (max_results={max_results})")

    # 검색 실행
    search_results = get_web_search(
        query,
        max_results=max_results,
        topic=topic,
        include_raw_content=True,
    )

    # 결과 처리 및 요약
    processed_results = process_search_results(query, search_results)
    summaries = []

    for result in processed_results:
        summaries.append(f"- [{result['title']}]({result['url']}): {result['summary']}")

    # 도구 메시지를 위한 요약 생성
    summary_text = f"""Found {len(processed_results)} result(s) for '{query}':
{chr(10).join(summaries)}"""

    logger.debug(f"[TOOL] tavily_search 결과 {len(processed_results)}건:\n{summary_text[:500]}")

    return Command(
        update={
            "messages": [ToolMessage(summary_text, tool_call_id=tool_call_id)],
        }
    )

@tool(parse_docstring=True)
def think_tool(reflection: str) -> str:
    """Tool for strategic reflection on research progress and decision-making.

    Use this tool after each search to analyze results and plan next steps systematically.

    When to use:
    - After receiving search results: What key information did I find?
    - Before deciding next steps: Do I have enough to answer comprehensively?
    - Before concluding research: Can I provide a complete answer now?

    Reflection should address:
    1. Analysis of current findings - What concrete information have I gathered?
    2. Gap assessment - What crucial information is still missing?
    3. Quality evaluation - Do I have sufficient evidence/examples for a good answer?
    4. Strategic decision - Should I continue searching or provide my answer?

    Args:
        reflection: Your detailed reflection on research progress, findings, gaps, and next steps

    Returns:
        Confirmation that reflection was recorded for decision-making"""
    logger.debug(f"[TOOL] think_tool 호출: {reflection[:200]}{'...' if len(reflection) > 200 else ''}")
    return f"Reflection recorded: {reflection}"

deep_search_agent_tools = [tavily_search, think_tool, guideline_search_tool]
deep_search_agent = {
    "name": "deep-search-agent",
    "description": "Delegate medical research to the sub-agent medical researcher. Only give this researcher one topic at a time.",
    "prompt": MEDICAL_RESEARCHER_INSTRUCTIONS,
    "tools": ["tavily_search", "think_tool", "guideline_search_tool"],
}