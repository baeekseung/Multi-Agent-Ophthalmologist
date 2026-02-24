from typing import Annotated, NotRequired, Literal, Optional
from langchain.agents import AgentState
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class Question(TypedDict):
    """A structured question item for tracking progress through consultation.

    Attributes:
        content: Short, specific description of the question
        status: Current state - pending, in_progress, or completed
    """
    content: str
    status: Literal["pending", "in_progress", "completed"]


class ExpertOpinion(BaseModel):
    expected_disease: list[str] = Field(
        description="The most likely ophthalmic disease or condition expected for the patient, inferred from the consultation conversation analysis. Provide specific disease names.")
    diagnosis_reasoning: str = Field(
        description="A clear and concise explanation for why the expected_disease was selected, based on the patient's consultation details and medical reasoning.")
    required_information: Optional[list[str]] = Field(
        default=None,
        description="Additional information or responses that the patient should provide to improve diagnostic certainty. List specific questions or details needed. If no additional information is needed, set to None.")


class ConsensusDecision(BaseModel):
    consensus_reached: bool = Field(
        description="Whether the expert consensus has been reached based on the expert opinions. True if all experts agree on the expected disease, False otherwise.")
    reasoning: str = Field(
        description="The rationale for the supervisor's decision to reach consensus or not, based on the expert opinions and consultation summary.")


class FinalMidTermDiagnosisResult(BaseModel):
    diagnosis_result: str = Field(
        description="The final diagnosis result when consensus is reached, based on the expert opinions and consultation summary. Be sure to include: 1) a clear summary of the experts' opinions and their reasoning, 2) a detailed explanation of any additional information requested by the experts, specifying exactly what should be further asked of the patient and why, and 3) Whether additional analysis is required after collecting supplementary information.")
    consultation_sufficient: bool = Field(
        description="""진료상담 종료 여부 판단.
        True: 모든 전문의의 required_information이 None이고, 예상 질병이 1~2개로 명확하며,
              환자 기본정보(나이/성별/증상/과거력)가 모두 수집된 경우.
        False: 하나 이상의 전문의가 required_information을 제시하거나,
               감별 진단이 필요하거나, 핵심 정보가 누락된 경우. 불확실하면 False."""
    )


class SupervisorResponse(BaseModel):
    next_and_instruction: dict[Literal["expert1", "expert2", "expert3", "evaluate_consensus_agent", "summarize_consensus_agent"], str] = Field(
        description="""Determines the next node(s) to execute and the corresponding instructions for each node. Returns a dictionary mapping node names to instructions. The node name should be one of: expert1, expert2, expert3, evaluate_consensus_agent, or summarize_consensus_agent. The instruction is the message to be sent to the node."""
    )


class MainState(AgentState):
    consultation_next: NotRequired[str]
    consultation_summary: NotRequired[str]
    consultation_turn: NotRequired[int] = 1

    supervisor_messages: Annotated[list[AnyMessage], add_messages]
    expert1_messages: Annotated[list[AnyMessage], add_messages]
    expert2_messages: Annotated[list[AnyMessage], add_messages]
    expert3_messages: Annotated[list[AnyMessage], add_messages]
    round_number: NotRequired[int]
    
    mid_term_diagnosis_summary: NotRequired[str]
    expert_responses_received: NotRequired[int]
    expert_responses_expected: NotRequired[int]
    final_report: NotRequired[str]  # generate_final_report 노드가 생성하는 최종 진단서
