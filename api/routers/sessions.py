import asyncio
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from api.dependencies import get_graph, get_session_store
from api.exceptions import SessionAlreadyCompletedError, SessionNotFoundError
from api.schemas.session import (
    AnswerRequest,
    AnswerResponse,
    ConversationHistoryResponse,
    ConversationTurn,
    SessionResponse,
)
from app.prompts import INITIAL_CONSULTATION_MESSAGE
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/sessions", tags=["세션"])


def _extract_question(result: dict) -> Optional[str]:
    """LangGraph 실행 결과에서 interrupt 질문을 추출합니다."""
    interrupts = result.get("__interrupt__", [])
    if interrupts:
        return interrupts[0].value.get("question", "질문을 가져올 수 없습니다.")
    return None


@router.post("", response_model=SessionResponse)
async def start_consultation(request: Request):
    """
    [POST /sessions] 새 진료 세션 생성

    1. UUID로 고유한 session_id 생성
    2. LangGraph 실행 시작 → consultation_agent → patient_response(interrupt)
    3. interrupt에서 첫 번째 질문 추출 → 응답 반환
    """
    from api.config import settings

    graph = await get_graph(request)
    store = get_session_store()

    session_id = str(uuid4())
    config = {"configurable": {"thread_id": session_id}}
    initial_input = {
        "messages": [HumanMessage(
            content=(
                f"## previous_consultation_summary: 아직 진료상담 이력이 없습니다.\n\n"
                f"## expert_opinion: {INITIAL_CONSULTATION_MESSAGE}"
            ),
            name="expert",
        )],
        "consultation_turn": 1,
    }

    try:
        result = await asyncio.wait_for(
            graph.ainvoke(initial_input, config=config),
            timeout=settings.llm_timeout_seconds,
        )

        question = _extract_question(result)
        if question is None:
            raise ValueError("첫 번째 질문을 가져오지 못했습니다.")

        store[session_id] = {
            "session_id": session_id,
            "status": "patient response waiting",
            "current_question": question,
            "conversation_history": [],
            "final_report": None,
            "graph_config": config,
            "patient_info": {},
            "created_at": datetime.now(),
        }

        logger.info(f"[세션생성] session_id={session_id}")
        return SessionResponse(session_id=session_id, question=question, status="waiting")

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"LLM 응답 시간 초과 ({settings.llm_timeout_seconds}초)",
        )
    except Exception as e:
        logger.error(f"[세션생성 오류] {e}")
        raise HTTPException(status_code=500, detail=f"세션 생성 오류: {str(e)}")


@router.post("/{session_id}/answer", response_model=AnswerResponse)
async def submit_patient_answer(session_id: str, body: AnswerRequest, request: Request):
    """
    [POST /sessions/{session_id}/answer] 환자 답변 제출

    1. 세션 조회 + 상태 검증
    2. Command(resume=answer)로 interrupt된 그래프 재개
    3. 다음 interrupt → 다음 질문 반환 / 없으면 → 완료 처리
    """
    from api.config import settings

    store = get_session_store()
    if session_id not in store:
        raise SessionNotFoundError(session_id)

    session = store[session_id]
    if session["status"] == "completed":
        raise SessionAlreadyCompletedError(session_id)

    graph = await get_graph(request)
    config = session["graph_config"]

    # graph.ainvoke 전에 현재 질문 + 답변 쌍을 대화내역에 저장
    turn_number = len(session.get("conversation_history", [])) + 1
    session.setdefault("conversation_history", []).append({
        "turn": turn_number,
        "question": session["current_question"],
        "answer": body.answer,
        "answered_at": datetime.now().isoformat(),
    })

    try:
        result = await asyncio.wait_for(
            graph.ainvoke(Command(resume={"answer": body.answer}), config=config),
            timeout=settings.llm_timeout_seconds,
        )

        next_question = _extract_question(result)

        if next_question:
            session["current_question"] = next_question
            return AnswerResponse(session_id=session_id, question=next_question, status="waiting")
        else:
            graph_state = await graph.aget_state(config)
            final_report = graph_state.values.get(
                "diagnosis_research_result",
                "진단 보고서가 생성되었습니다.",
            )
            session["status"] = "completed"
            session["final_report"] = final_report

            logger.info(f"[진단완료] session_id={session_id}")
            return AnswerResponse(
                session_id=session_id,
                status="completed",
                message=f"진단이 완료되었습니다. GET /sessions/{session_id}/report 에서 보고서를 확인하세요.",
            )

    except (SessionNotFoundError, SessionAlreadyCompletedError):
        raise
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"LLM 응답 시간 초과 ({settings.llm_timeout_seconds}초)",
        )
    except Exception as e:
        logger.error(f"[답변처리 오류] session_id={session_id}, {e}")
        raise HTTPException(status_code=500, detail=f"답변 처리 오류: {str(e)}")


@router.get("/{session_id}/conversation", response_model=ConversationHistoryResponse)
async def get_conversation_history(session_id: str):
    """[GET /sessions/{session_id}/conversation] 세션의 누적 대화내역 조회"""
    store = get_session_store()
    if session_id not in store:
        raise SessionNotFoundError(session_id)

    session = store[session_id]
    history = session.get("conversation_history", [])
    return ConversationHistoryResponse(
        session_id=session_id,
        status=session["status"],
        total_turns=len(history),
        conversation=[ConversationTurn(**t) for t in history],
    )


@router.get("/{session_id}/status")
async def get_session_status(session_id: str):
    """[GET /sessions/{session_id}/status] 세션 현재 상태 조회"""
    store = get_session_store()
    if session_id not in store:
        raise SessionNotFoundError(session_id)

    session = store[session_id]
    return {
        "session_id": session["session_id"],
        "status": session["status"],
        "current_question": session["current_question"],
        "patient_info": session["patient_info"],
        "has_report": session["final_report"] is not None,
    }
