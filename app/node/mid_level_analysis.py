import json
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.types import Command, Send
from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents import create_agent
from langchain_core.prompts import ChatPromptTemplate

from app.state import MainState, ConsensusDecision, FinalMidTermDiagnosisResult, SupervisorResponse, ExpertOpinion
from app.prompts import (
    SUPERVISOR_AGENT_PROMPT,
    EXPERT_OPINION_PROMPT,
    EVALUATION_CONSENSUS_PROMPT,
    SUMMARIZE_CONSENSUS_PROMPT,
)
from app.utils.messages_pretty_print import messages_pretty_print
from app.utils.logger import get_logger
from app.mcp.sequential_thinking_tool import sequential_thinking_tools

from functools import partial

logger = get_logger(__name__)

MAX_RECONSULT_ROUNDS = 3
_MINI_LLM = ChatOpenAI(model="gpt-4o-mini", temperature=0)

async def create_expert_node(state: MainState, expert_name: str, model) -> Command:
    expert_messages = state.get(f"{expert_name}_messages", [])
    logger.info(f"[NODE] {expert_name} 에이전트 시작 (메시지 {len(expert_messages)}건)")
    logger.debug(f"[NODE] {expert_name} 메시지:\n{messages_pretty_print(expert_messages)}")

    async with sequential_thinking_tools() as tools:
        expert_agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=EXPERT_OPINION_PROMPT,
            state_schema=MainState,
            response_format=ExpertOpinion,
        )

        response = await expert_agent.ainvoke({"messages": expert_messages})

    return Command(
        update={
            f"{expert_name}_messages": response["messages"],
            "supervisor_messages": [
                HumanMessage(
                    content=f"[{expert_name} opinion]:\n{response['messages'][-1].content}",
                    name=expert_name,
                )
            ],
        },
        goto="supervisor",
    )

expert1_agent = partial(create_expert_node, expert_name="expert1", model=ChatOpenAI(model="gpt-4o-mini", temperature=0.1))
expert2_agent = partial(create_expert_node, expert_name="expert2", model=ChatOpenAI(model="gpt-4o-mini", temperature=0.2))
expert3_agent = partial(create_expert_node, expert_name="expert3", model=ChatOpenAI(model="gpt-4o-mini", temperature=0.3))
# expert2_agent = partial(create_expert_node, expert_name="expert2", model=ChatAnthropic(model="claude-sonnet-4-6", temperature=0.1))
# expert3_agent = partial(create_expert_node, expert_name="expert3", model=ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.1))

# 전문의 이름 리스트 (문자열)
EXPERT_NAMES = ["expert1", "expert2", "expert3"]

async def evaluate_consensus_agent(state: MainState) -> Command:
    """전문의 의견을 평가하여 합의 여부를 판단."""
    logger.info("[NODE] evaluate_consensus_agent 시작")

    expert_opinions = ""
    for name in EXPERT_NAMES:
        messages = state.get(f'{name}_messages', [])
        if messages:
            expert_opinions += f"[{name} Opinion]\n{messages[-1].content}\n\n"

    logger.debug(f"전문의 의견:\n{expert_opinions}")

    structured_llm = _MINI_LLM.with_structured_output(ConsensusDecision)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", EVALUATION_CONSENSUS_PROMPT),
            ("user", "## expert_opinions:\n{expert_opinions}"),
        ]
    )

    chain = prompt | structured_llm
    response: ConsensusDecision = await chain.ainvoke({"expert_opinions": expert_opinions})

    # ConsensusDecision을 메시지 형식으로 포맷팅
    content = (
        f"[Consensus Evaluation Result]\n"
        f"합의 도달: {'합의 도달' if response.consensus_reached else '합의 미달'}\n"
        f"결정 근거: {response.reasoning}\n"
    )

    logger.info(f"[NODE] evaluate_consensus_agent 완료\n{content}")

    return Command(
        update={
            "supervisor_messages": [HumanMessage(content=content, name="evaluate_consensus_agent")],
        },
        goto="supervisor",
    )

async def summarize_consensus_agent(state: MainState) -> Command:
    logger.info("[NODE] summarize_consensus_agent 시작")
    supervisor_messages = state.get("supervisor_messages", [])
    consultation_summary = state.get("consultation_summary", "")
    consultation_turn = state.get("consultation_turn", 1)

    # 현재 중간분석 턴의 시작 인덱스 (없으면 0 - 첫 번째 턴)
    turn_start = state.get("supervisor_messages_turn_start", 0)
    current_turn_messages = supervisor_messages[turn_start:]

    # 현재 턴에 해당하는 메시지만 추출
    chat_history = ""
    for m in current_turn_messages:
        if m.name == "expert1":
            chat_history += f"[expert1 opinion]\n{m.content}\n\n"
        elif m.name == "expert2":
            chat_history += f"[expert2 opinion]\n{m.content}\n\n"
        elif m.name == "expert3":
            chat_history += f"[expert3 opinion]\n{m.content}\n\n"
        elif m.name == "supervisor":
            chat_history += f"[supervisor instruction]\n{m.content}\n\n"
        else:
            continue

    structured_llm = _MINI_LLM.with_structured_output(FinalMidTermDiagnosisResult)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SUMMARIZE_CONSENSUS_PROMPT),
            ("user", "## chat_history:\n{chat_history}"),
        ]
    )

    chain = prompt | structured_llm
    response: FinalMidTermDiagnosisResult = await chain.ainvoke({"chat_history": chat_history})

    logger.info(f"[NODE] summarize_consensus_agent 완료 | 상담 충분: {response.consultation_sufficient}")
    logger.debug(f"최종 진단 합의본:\n{response.diagnosis_result}")

    if response.consultation_sufficient:
        # 상담 충분 → 진단서 생성 후 종료
        return Command(
            update={
                "mid_term_diagnosis_summary": response.diagnosis_result,
                "supervisor_messages": [HumanMessage(content=f"{consultation_turn}번째 Mid-level analysis 결과: {response.diagnosis_result}", name="summarize_consensus_agent")],
            },
            goto="diagnosis_agent",
        )
    else:
        # 추가 상담 필요 → consultation_agent 복귀
        expert_opinion_message = (
            f"## expert_opinion: {response.diagnosis_result}\n\n"
            f"## previous_consultation_summary: {consultation_summary}"
        )

        next_turn_start = len(supervisor_messages) + 1
        return Command(
            update={
                "mid_term_diagnosis_summary": response.diagnosis_result,
                "messages": [HumanMessage(content=expert_opinion_message, name="expert")],
                "supervisor_messages": [HumanMessage(content=f"{consultation_turn}번째 Mid-level analysis 결과: {response.diagnosis_result}\n\n분석한 결과를 기반으로 추가적인 진료 상담을 진행합니다.", name="summarize_consensus_agent")],
                "supervisor_messages_turn_start": next_turn_start,
                "consultation_turn": consultation_turn + 1,
            },
            goto="consultation_agent",
        )

MEMBERS = ["evaluate_consensus_agent", "summarize_consensus_agent"] + EXPERT_NAMES

async def supervisor_agent_node(state: MainState) -> Command:
    round_number = state.get("round_number", 0)
    supervisor_messages = state.get("supervisor_messages", [])
    consultation_summary = state.get("consultation_summary", "")
    mid_term_diagnosis_summary = state.get("mid_term_diagnosis_summary", "")
    consultation_turn = state.get("consultation_turn", 1)

    logger.info(f"[NODE] supervisor 시작 (라운드 {round_number}, 메시지 {len(supervisor_messages)}건)")
    logger.debug(f"[NODE] supervisor 메시지:\n{messages_pretty_print(supervisor_messages)}")

    # 최대 재질의 횟수 초과 시 다수결 기반 종합
    if round_number >= MAX_RECONSULT_ROUNDS:
        logger.warning(f"[NODE] supervisor - 최대 재질의 횟수({MAX_RECONSULT_ROUNDS}) 도달. 다수결 종합 실행")

        # 각 전문의 마지막 의견 수집하여 불일치 사유와 함께 summarize에 전달
        disagreement_summary = ""
        for name in EXPERT_NAMES:
            msgs = state.get(f"{name}_messages", [])
            if msgs:
                last = msgs[-1].content if hasattr(msgs[-1], "content") else str(msgs[-1])
                disagreement_summary += f"[{name} 최종 의견]\n{last[:300]}\n\n"

        fallback_instruction = (
            f"최대 재질의 횟수({MAX_RECONSULT_ROUNDS}회)에 도달했습니다.\n"
            f"전문의 간 완전한 합의에 도달하지 못했으므로, 다수 의견을 기준으로 종합 분석을 작성합니다.\n"
            f"불일치 사유와 각 전문의 의견을 명시하고, 가장 유력한 진단 방향으로 요약하세요.\n\n"
            f"[전문의별 최종 의견 요약]\n{disagreement_summary}"
        )

        return Command(
            goto="summarize_consensus_agent",
            update={
                "supervisor_messages": [AIMessage(content=fallback_instruction, name="supervisor")],
                "round_number": 0
            }
        )

    llm = ChatOpenAI(model="gpt-4o", temperature=0.1)
    agent = create_agent(
        model=llm,
        tools=[],
        system_prompt=SUPERVISOR_AGENT_PROMPT,
        response_format=SupervisorResponse
    )

    response = await agent.ainvoke({"messages": supervisor_messages})
    response_json = json.loads(response['messages'][-1].content)

    # SupervisorResponse 파싱
    next_and_instruction = response_json['next_and_instruction']
    next_nodes = list(next_and_instruction.keys())

    logger.info(f"[NODE] supervisor 결정 → {next_nodes}")
    logger.debug(f"[NODE] supervisor 지시 내용:\n{response_json['next_and_instruction']}")

    # 여러 노드에 동시 요청 (fan-out, 주로 초기 라운드)
    if len(next_nodes) > 1:
        logger.info(f"[NODE] supervisor fan-out → {next_nodes}")
        sends = []
        supervisor_update_messages_content = ""

        for node_name, instruction in next_and_instruction.items():
            if node_name in EXPERT_NAMES:
                # 2차+ 라운드: 이전 중간분석 내용과 추가 상담 내용을 함께 제공하여 진단 갱신 요청
                if mid_term_diagnosis_summary:
                    instruction_content = (
                        f"## {consultation_turn-1}번째 Mid-level analysis 결과:\n{mid_term_diagnosis_summary}\n\n"
                        f"## 추가 수집된 진료상담 내용:\n{consultation_summary}\n\n"
                        f"## supervisor's instruction:\n{instruction}"
                    )
                else:
                    instruction_content = (
                        f"## consultation_summary:\n{consultation_summary}\n\n"
                        f"## supervisor's instruction:\n{instruction}"
                    )
                existing_messages = state.get(f"{node_name}_messages", [])
                sends.append(Send(
                    node_name,
                    {f"{node_name}_messages": existing_messages + [HumanMessage(content=instruction_content, name="supervisor")]}
                ))
                supervisor_update_messages_content += f"[Supervisor -> {node_name}] - Instruction: {instruction}\n"

        if sends:
            return Command(
                goto=sends,
                update={
                    "supervisor_messages": [AIMessage(content=supervisor_update_messages_content, name="supervisor")],
                    "round_number": round_number + 1
                }
            )

    # 단일 노드 요청
    next_node = next_nodes[0]
    instruction = next_and_instruction[next_node]

    # evaluate_consensus_agent 호출
    if next_node == "evaluate_consensus_agent":
        return Command(
            goto="evaluate_consensus_agent",
            update={
                "supervisor_messages": [
                    AIMessage(content=f"[Supervisor -> evaluate_consensus_agent]\n{instruction}", name="supervisor")
                ]
            }
        )

    # summarize_consensus_agent 호출
    elif next_node == "summarize_consensus_agent":
        return Command(
            goto="summarize_consensus_agent",
            update={
                "supervisor_messages": [
                    AIMessage(content=f"[Supervisor -> summarize_consensus_agent]\n{instruction}", name="supervisor")
                ],
                "round_number": 0,
            }
        )

    # 특정 expert에게 재질의
    elif next_node in EXPERT_NAMES:
        return Command(
            goto=next_node,
            update={
                f"{next_node}_messages": [HumanMessage(content=instruction, name="supervisor")],
                "supervisor_messages": [
                    AIMessage(content=f"[Supervisor -> {next_node}]\n{instruction}", name="supervisor")
                ],
                "round_number": round_number + 1
            }
        )

    else:
        raise ValueError(f"Unknown next node: {next_node}. Expected one of {MEMBERS}")