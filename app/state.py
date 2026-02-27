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
        description="supervisor와 expert들의 대화에서 합의된 분석내용을 한국어로 작성합니다. 분석에서 결정된 환자의 예상질병, 그에 대한 근거를 명확하게 작성합니다. 만약  expert들이 요청한 추가 정보가 존재한다면 내용에 포함시켜 작성합니다.")
    consultation_sufficient: bool = Field(
        description="""전문의들이 추가로 요청한 정보존재 여부를 기반으로 진료상담을 종료할지 여부를 결정합니다.
        True: 모든 전문의의 마지막 의견에서 required_information이 None인 경우
        False: 하나 이상의 전문의가 required_information을 제시한 경우"""
    )


class SupervisorResponse(BaseModel):
    next_and_instruction: dict[Literal["expert1", "expert2", "expert3", "evaluate_consensus_agent", "summarize_consensus_agent"], str] = Field(
        description="""Determines the next node(s) to execute and the corresponding instructions for each node. Returns a dictionary mapping node names to instructions. The node name should be one of: expert1, expert2, expert3, evaluate_consensus_agent, or summarize_consensus_agent. The instruction is the message to be sent to the node."""
    )

class Todo(TypedDict):
    """A structured task item for tracking progress through complex workflows.

    Attributes:
        content: Short, specific description of the task
        status: Current state - pending, in_progress, or completed
    """

    content: str
    status: Literal["pending", "in_progress", "completed"]


class MainState(AgentState):
    consultation_next: NotRequired[str]
    consultation_summary: NotRequired[str]
    consultation_turn: NotRequired[int] = 1

    supervisor_messages: Annotated[list[AnyMessage], add_messages]
    supervisor_messages_turn_start: NotRequired[int]  # 현재 중간분석 턴의 시작 인덱스 (기본값 0)
    expert1_messages: Annotated[list[AnyMessage], add_messages]
    expert2_messages: Annotated[list[AnyMessage], add_messages]
    expert3_messages: Annotated[list[AnyMessage], add_messages]
    round_number: NotRequired[int]
    
    mid_term_diagnosis_summary: NotRequired[str]
    expert_responses_received: NotRequired[int]
    expert_responses_expected: NotRequired[int]
    diagnosis_research_result: NotRequired[str]  # diagnosis_agent가 생성한 심층 연구 결과
    final_report: NotRequired[str]  # generate_final_report 노드가 생성하는 최종 진단서


def file_reducer(left, right):
    if left is None:
        return right
    elif right is None:
        return left
    else:
        return {**left, **right}


class DeepAgentState(AgentState):
    """Extended agent state that includes task tracking and virtual file system.

    Inherits from LangGraph's AgentState and adds:
    - todos: List of Todo items for task planning and progress tracking
    - files: Virtual file system stored as dict mapping filenames to content
    """

    # 작업 플래닝 및 진행 상황 추적을 위한 Todo 리스트 필드
    todos: NotRequired[list[Todo]]
    # 파일명과 내용 매핑, file_reducer로 병합되는 가상 파일 시스템 필드
    files: Annotated[NotRequired[dict[str, str]], file_reducer]
