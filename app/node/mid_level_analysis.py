from dotenv import load_dotenv
load_dotenv()

import json
from langchain_openai import ChatOpenAI
from langgraph.types import Command, Send
from langchain_core.messages import HumanMessage, AIMessage, RemoveMessage
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

from functools import partial

# 최대 반복 횟수
MAX_RECONSULT_ROUNDS = 3

async def create_expert_node(state: MainState, expert_name: str, model) -> Command:
    print(f"AGENT CALLED: {expert_name} agent called")
    expert_messages = state.get(f"{expert_name}_messages", [])
    print(f"## {expert_name} messages: {messages_pretty_print(expert_messages)}\n")
    expert_agent = create_agent(
        model=model,
        tools=[],
        system_prompt=EXPERT_OPINION_PROMPT,
        state_schema=MainState,
        response_format=ExpertOpinion
    )
    response = await expert_agent.ainvoke({"messages": expert_messages})

    return Command(
        update={
            # f"{expert_name}_messages": [AIMessage(content=response["messages"][-1].content, name=expert_name)],
            f"{expert_name}_messages": response['messages'],
            "supervisor_messages": [HumanMessage(content=f"[{expert_name} opinion]:\n{response['messages'][-1].content}", name=expert_name)],
        },
        goto="supervisor",
    )

expert1_agent = partial(create_expert_node, expert_name="expert1", model=ChatOpenAI(model="gpt-4o", temperature=0.1))
expert2_agent = partial(create_expert_node, expert_name="expert2", model=ChatOpenAI(model="gpt-4o", temperature=0.5))
expert3_agent = partial(create_expert_node, expert_name="expert3", model=ChatOpenAI(model="gpt-4o", temperature=0.9))

# 전문의 이름 리스트 (문자열)
EXPERT_NAMES = ["expert1", "expert2", "expert3"]

async def evaluate_consensus_agent(state: MainState) -> Command:
    """전문의 의견을 평가하여 합의 여부를 판단."""
    print(f"[AGENT CALLED]: evaluate_consensus called")

    expert_opinions = ""
    for name in EXPERT_NAMES:
        messages = state.get(f'{name}_messages', [])
        if messages:
            expert_opinions += f"[{name} Opinion]\n{messages[-1].content}\n\n"

    print(f"## Expert opinions:\n{expert_opinions}\n")

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    structured_llm = llm.with_structured_output(ConsensusDecision)

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

    print(f"## Evaluate consensus result:\n{content}\n")

    return Command(
        update={
            "supervisor_messages": [HumanMessage(content=content, name="evaluate_consensus_agent")],
        },
        goto="supervisor",
    )

async def summarize_consensus_agent(state: MainState) -> Command:
    print(f"[AGENT CALLED]: Summarize consensus called")
    supervisor_messages = state.get("supervisor_messages", [])
    consultation_summary = state.get("consultation_summary", "")
    consultation_turn = state.get("consultation_turn", 1)

    # supervisor_messages에서 전문의 의견과 supervisor 지시사항 추출
    chat_history = ""
    for m in supervisor_messages:
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

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    structured_llm = llm.with_structured_output(FinalMidTermDiagnosisResult)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SUMMARIZE_CONSENSUS_PROMPT),
            ("user", "## chat_history:\n{chat_history}"),
        ]
    )

    chain = prompt | structured_llm
    response: FinalMidTermDiagnosisResult = await chain.ainvoke({"chat_history": chat_history})

    print(f"## SUMMARIZE_CONSENSUS: Final diagnosis result:\n{response.diagnosis_result}")
    print(f"## SUMMARIZE_CONSENSUS: Consultation sufficient: {response.consultation_sufficient}")

    # supervisor_messages 초기화 (공통)
    # remove_supervisor_messages = [RemoveMessage(id=m.id) for m in state.get("supervisor_messages", [])]

    if response.consultation_sufficient:
        # 상담 충분 → 진단서 생성 후 종료
        return Command(
            update={
                "mid_term_diagnosis_summary": response.diagnosis_result,
                "supervisor_messages": [HumanMessage(content=f"이번 Mid-level analysis 결과: {response.diagnosis_result}", name="summarize_consensus_agent")],
            },
            goto="diagnosis_agent",
        )
    else:
        # 추가 상담 필요 → consultation_agent 복귀
        expert_opinion_message = (
            f"## previous_consultation_summary: {consultation_summary}\n\n"
            f"## expert_opinion: {response.diagnosis_result}"
        )
        # 2차 라운드 시작 전 expert 메시지도 초기화하여 supervisor가 라운드를 명확히 구분하도록 함
        # remove_expert1 = [RemoveMessage(id=m.id) for m in state.get("expert1_messages", [])]
        # remove_expert2 = [RemoveMessage(id=m.id) for m in state.get("expert2_messages", [])]
        # remove_expert3 = [RemoveMessage(id=m.id) for m in state.get("expert3_messages", [])]
        return Command(
            update={
                "mid_term_diagnosis_summary": response.diagnosis_result,
                "messages": [HumanMessage(content=expert_opinion_message, name="expert")],
                "supervisor_messages": [HumanMessage(content=f"{consultation_turn}번째 Mid-level analysis 결과: {response.diagnosis_result}\n\n추가적으로 요청하신 질문에 대해 답변을 받아 다시 Mid-level analysis를 진행합니다.", name="summarize_consensus_agent")],
                "consultation_turn": consultation_turn + 1,
                # "expert1_messages": remove_expert1,
                # "expert2_messages": remove_expert2,
                # "expert3_messages": remove_expert3,
            },
            goto="consultation_agent",
        )

MEMBERS = ["evaluate_consensus_agent", "summarize_consensus_agent"] + EXPERT_NAMES

async def supervisor_agent_node(state: MainState) -> Command:
    print(f"[AGENT CALLED]: Mid-level analysis supervisor agent called")
    round_number = state.get("round_number", 0)
    supervisor_messages = state.get("supervisor_messages", [])
    print(messages_pretty_print(supervisor_messages))
    consultation_summary = state.get("consultation_summary", "")
    mid_term_diagnosis_summary = state.get("mid_term_diagnosis_summary", "")
    consultation_turn = state.get("consultation_turn", 1)

    # 최대 재질의 횟수 초과 시 강제 종합
    if round_number >= MAX_RECONSULT_ROUNDS:
        print(f"SUPERVISOR: Maximum reconsult rounds reached. Forcing consensus summary.\n")
        return Command(
            goto="summarize_consensus_agent",
            update={
                "supervisor_messages": [AIMessage(content=f"최대 반복 횟수에 도달했습니다. {consultation_turn}번째 Mid-level analysis 결과를 작성합니다.", name="supervisor")],
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

    print(f"## Supervisor response next_and_instruction:\n{response_json['next_and_instruction']}\n")

    # SupervisorResponse 파싱
    next_and_instruction = response_json['next_and_instruction']
    next_nodes = list(next_and_instruction.keys())

    # 여러 노드에 동시 요청 (fan-out, 주로 초기 라운드)
    if len(next_nodes) > 1:
        print(f"## SUPERVISOR: Fan-out to multiple nodes: {next_nodes}\n")
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