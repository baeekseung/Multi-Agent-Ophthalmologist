from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.prompts import REPORT_EVALUATOR_PROMPT
from app.state import MainState
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ReportEvaluation(BaseModel):
    evidence_quality: int = Field(description="근거 충분성 점수 (1-5)", ge=1, le=5)
    clinical_completeness: int = Field(description="임상 완성도 점수 (1-5)", ge=1, le=5)
    hallucination_risk: int = Field(description="환각 위험도 점수 (1-5)", ge=1, le=5)
    clinical_utility: int = Field(description="실용성 점수 (1-5)", ge=1, le=5)
    structure_completeness: int = Field(description="구조 완성도 점수 (1-5)", ge=1, le=5)
    total_score: int = Field(description="총점 (5-25)")
    flags: list[str] = Field(default_factory=list, description="환각 의심 또는 주의 항목 목록")
    improvement_suggestions: str = Field(description="개선 권고사항")
    overall_grade: str = Field(description="종합 등급 (A/B/C/D)")


async def report_evaluator_node(state: MainState) -> Command:
    """LLM-as-Judge 패턴으로 최종 진단 보고서의 품질을 자동 평가합니다."""
    logger.info("[NODE] report_evaluator 시작 - 진단 보고서 품질 평가")

    diagnosis_result = state.get("diagnosis_research_result", "")
    if not diagnosis_result:
        logger.warning("[NODE] report_evaluator: diagnosis_research_result가 비어있음. 평가 건너뜀.")
        return Command(
            update={"evaluation_result": {"skipped": True, "reason": "진단 보고서 없음"}},
            goto=END,
        )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(ReportEvaluation)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", REPORT_EVALUATOR_PROMPT),
            ("user", "## 평가 대상 진단 보고서:\n\n{report}"),
        ]
    )

    chain = prompt | structured_llm
    evaluation: ReportEvaluation = await chain.ainvoke({"report": diagnosis_result})

    evaluation_dict = evaluation.model_dump()

    logger.info(
        f"[NODE] report_evaluator 완료 | "
        f"등급: {evaluation.overall_grade} | "
        f"총점: {evaluation.total_score}/25 | "
        f"환각 플래그: {len(evaluation.flags)}건"
    )

    if evaluation.flags:
        logger.warning(f"[NODE] report_evaluator 환각 의심 항목:\n" + "\n".join(f"  - {f}" for f in evaluation.flags))

    logger.debug(
        f"평가 상세:\n"
        f"  근거 충분성: {evaluation.evidence_quality}/5\n"
        f"  임상 완성도: {evaluation.clinical_completeness}/5\n"
        f"  환각 위험도: {evaluation.hallucination_risk}/5\n"
        f"  실용성: {evaluation.clinical_utility}/5\n"
        f"  구조 완성도: {evaluation.structure_completeness}/5\n"
        f"  개선 권고: {evaluation.improvement_suggestions}"
    )

    return Command(
        update={"evaluation_result": evaluation_dict},
        goto=END,
    )
