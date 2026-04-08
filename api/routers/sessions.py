import asyncio
import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
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

# 분석 단계 노드 집합: 이 노드 중 하나가 먼저 오면 분석 시작으로 판단
ANALYSIS_NODES = {
    "supervisor", "expert1", "expert2", "expert3",
    "evaluate_consensus_agent", "summarize_consensus_agent", "diagnosis_agent",
}

# 노드별 한국어 레이블
NODE_LABELS = {
    "supervisor":                {"title": "슈퍼바이저 분석 조율",  "phase": "mid_analysis"},
    "expert1":                   {"title": "전문의 A 소견 분석",    "phase": "mid_analysis"},
    "expert2":                   {"title": "전문의 B 소견 분석",    "phase": "mid_analysis"},
    "expert3":                   {"title": "전문의 C 소견 분석",    "phase": "mid_analysis"},
    "evaluate_consensus_agent":  {"title": "전문의 합의 평가",      "phase": "mid_analysis"},
    "summarize_consensus_agent": {"title": "중간 분석 종합",        "phase": "mid_analysis"},
    "diagnosis_agent":           {"title": "심층 진단 연구 완료",   "phase": "deep_diagnosis"},
}

# 서브에이전트 한국어 레이블
_SUBAGENT_KR = {
    "deep-search-agent":        "의학 문헌 검색",
    "information-analysis-agent": "정보 분석",
    "organize-agent":           "결과 정리",
    "write-agent":              "보고서 작성",
}

# 노드별 완료 설명
_NODE_DESC = {
    "supervisor":                "전문의 팀에게 분석 지시사항을 전달했습니다.",
    "expert1":                   "전문의 A가 증상을 검토하고 소견을 작성했습니다.",
    "expert2":                   "전문의 B가 증상을 검토하고 소견을 작성했습니다.",
    "expert3":                   "전문의 C가 증상을 검토하고 소견을 작성했습니다.",
    "evaluate_consensus_agent":  "전문의들의 소견을 종합하여 합의 여부를 평가했습니다.",
    "summarize_consensus_agent": "중간 분석 결과를 종합했습니다.",
    "diagnosis_agent":           "심층 진단 연구 에이전트가 분석을 완료했습니다.",
}


def _sse_event(event_type: str, data: dict) -> str:
    """SSE 이벤트 문자열 생성"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_heartbeat() -> str:
    """SSE 하트비트 (연결 유지용 주석)"""
    return ": heartbeat\n\n"


def _extract_detail(node_name: str, updates: dict) -> Optional[str]:
    """노드 업데이트에서 진행 상세 정보 추출"""
    if node_name == "supervisor":
        # round_number=1은 첫 fan-out 결과 → 재질의 아님
        # round_number>=2 부터가 실제 재질의
        round_num = updates.get("round_number")
        if round_num is not None and round_num >= 2:
            return f"라운드 {round_num} — 전문의 재질의 진행 중"
        return None

    elif node_name in ("expert1", "expert2", "expert3"):
        # expert는 supervisor_messages에 "[expertN opinion]: {json}" 형태의 문자열로 저장
        msgs = updates.get("supervisor_messages") or []
        if msgs:
            last = msgs[-1]
            content = getattr(last, "content", None) or ""
            if isinstance(content, str):
                # "[expert1 opinion]:\n{...}" 형태에서 JSON 파트 추출
                json_start = content.find("{")
                if json_start != -1:
                    try:
                        opinion = json.loads(content[json_start:])
                        diseases = opinion.get("expected_disease", [])
                        reasoning = opinion.get("diagnosis_reasoning", "")
                        if isinstance(diseases, list):
                            disease_str = ", ".join(diseases)
                        else:
                            disease_str = str(diseases)
                        if disease_str:
                            # reasoning 앞 100자
                            reason_short = reasoning[:100] + ("…" if len(reasoning) > 100 else "")
                            return f"예상 진단: {disease_str}\n{reason_short}"
                    except (json.JSONDecodeError, AttributeError):
                        # JSON 파싱 실패 시 원본 앞 120자
                        return content[:120]
        return None

    elif node_name == "evaluate_consensus_agent":
        msgs = updates.get("supervisor_messages") or []
        if msgs:
            last = msgs[-1]
            content = getattr(last, "content", None) or ""
            if "consensus_reached" in content.lower() or "합의" in content:
                pass
        # consensus_reached 필드는 structured output이라 updates에 직접 없음
        # 메시지 내용으로 판단
        for msg in reversed(msgs):
            c = getattr(msg, "content", "") or ""
            if "합의" in c and ("달성" in c or "True" in c or "true" in c):
                return "합의 달성"
            if "추가" in c or "False" in c or "false" in c:
                return "추가 검토 필요"
        return None

    elif node_name == "summarize_consensus_agent":
        # mid_term_diagnosis_summary 필드에 진단 결과가 저장됨
        summary = updates.get("mid_term_diagnosis_summary", "")
        if summary:
            short = summary[:80] + ("…" if len(summary) > 80 else "")
            return short
        return None

    elif node_name == "diagnosis_agent":
        return "심층 진단 연구 완료"
    return None


def _extract_rich_content(node_name: str, updates: dict) -> Optional[str]:
    """우측 피드용 전문 내용 추출 (좌측 타임라인 detail보다 상세)"""
    updates = updates or {}

    if node_name in ("expert1", "expert2", "expert3"):
        msgs = updates.get("supervisor_messages") or []
        if not msgs:
            return None
        raw = getattr(msgs[-1], "content", "") or ""
        json_start = raw.find("{")
        if json_start == -1:
            return raw or None
        try:
            opinion = json.loads(raw[json_start:])
            diseases = opinion.get("expected_disease", [])
            reasoning = opinion.get("diagnosis_reasoning", "")
            required = opinion.get("required_information", None)

            lines = []
            if diseases:
                d_str = ", ".join(diseases) if isinstance(diseases, list) else str(diseases)
                lines.append(f"예상 진단명\n{d_str}")
            if reasoning:
                lines.append(f"진단 근거\n{reasoning}")
            if required:
                if isinstance(required, list):
                    r_str = "\n".join(f"• {r}" for r in required)
                else:
                    r_str = str(required)
                lines.append(f"추가 필요 정보\n{r_str}")
            return "\n\n".join(lines) if lines else None
        except (json.JSONDecodeError, AttributeError):
            return raw[:500] or None

    elif node_name == "supervisor":
        msgs = updates.get("supervisor_messages") or []
        round_num = updates.get("round_number")
        lines = []
        # round_number=1은 첫 fan-out, >=2부터 재질의
        if round_num is not None and round_num >= 2:
            lines.append(f"분석 라운드\n{round_num}차 (재질의)")
        if msgs:
            raw = getattr(msgs[-1], "content", "") or ""
            # 내용 전체를 그대로 표시 (각 전문의 지시사항 레이블 포함)
            if raw:
                lines.append(f"전문의 지시사항\n{raw}")
        return "\n\n".join(lines) if lines else None

    elif node_name == "evaluate_consensus_agent":
        msgs = updates.get("supervisor_messages") or []
        if msgs:
            raw = getattr(msgs[-1], "content", "") or ""
            # JSON 포함 시 파싱 시도
            json_start = raw.find("{")
            if json_start != -1:
                try:
                    parsed = json.loads(raw[json_start:])
                    reached = parsed.get("consensus_reached")
                    reasoning = parsed.get("reasoning", "")
                    result_str = "✓ 합의 달성" if reached else "✗ 합의 미달성"
                    return f"합의 여부: {result_str}\n\n평가 근거\n{reasoning}" if reasoning else f"합의 여부: {result_str}"
                except (json.JSONDecodeError, AttributeError):
                    pass
            return raw or None
        return None

    elif node_name == "summarize_consensus_agent":
        summary = updates.get("mid_term_diagnosis_summary", "")
        msgs = updates.get("supervisor_messages") or []
        lines = []
        if summary:
            lines.append(f"종합 분석 결과\n{summary}")
        # consultation_sufficient 판단: goto 필드가 없으므로 메시지로 추정
        for msg in reversed(msgs):
            c = getattr(msg, "content", "") or ""
            if "심층 분석 시작" in c or "diagnosis_agent" in c:
                lines.append("판정: 상담 충분 → 심층 진단 진행")
                break
            if "추가 상담" in c or "consultation_agent" in c:
                lines.append("판정: 추가 상담 필요 → 재상담 진행")
                break
        return "\n\n".join(lines) if lines else summary or None

    return None


def _chunk_to_sse_events(mode: str, chunk: dict) -> list[str]:
    """LangGraph 청크를 SSE 이벤트 문자열 목록으로 변환"""
    ts = datetime.now().isoformat()
    events = []

    if mode == "updates":
        for node_name, updates in chunk.items():
            if node_name not in NODE_LABELS:
                continue
            meta = NODE_LABELS[node_name]
            updates = updates or {}
            detail = _extract_detail(node_name, updates)

            # supervisor: round_number>=2 일 때만 "(라운드 X 재질의)" 표기
            title = meta["title"]
            round_num = updates.get("round_number")
            if node_name == "supervisor" and round_num is not None and round_num >= 2:
                title = f"슈퍼바이저 분석 조율 (라운드 {round_num} 재질의)"

            rich = _extract_rich_content(node_name, updates)
            payload = {
                "node": node_name,
                "phase": meta["phase"],
                "title": title,
                "description": _NODE_DESC.get(node_name, "완료"),
                "timestamp": ts,
            }
            if detail:
                payload["detail"] = detail
            if rich:
                payload["content"] = rich
            events.append(_sse_event("node_progress", payload))

    elif mode == "custom":
        event_name = chunk.get("event_name", "")
        subagent_type = chunk.get("subagent_type", "")
        subagent_kr = _SUBAGENT_KR.get(subagent_type, subagent_type)
        if event_name == "subagent_start":
            events.append(_sse_event("diagnosis_subtask", {
                "status": "started",
                "subagent": subagent_type,
                "title": f"서브에이전트 시작: {subagent_kr}",
                "timestamp": ts,
            }))
        elif event_name == "subagent_complete":
            events.append(_sse_event("diagnosis_subtask", {
                "status": "completed",
                "subagent": subagent_type,
                "title": f"서브에이전트 완료: {subagent_kr}",
                "saved_files": chunk.get("saved_files", []),
                "timestamp": ts,
            }))

    return events


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
    2. astream으로 그래프 재개 — 첫 청크로 경로 분기:
       - __interrupt__ 도착 → 다음 질문 반환 (status: "waiting")
       - 분석 노드 도착 → 백그라운드 스트리밍 시작 (status: "analyzing")
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

    # 현재 질문 + 답변 쌍을 대화내역에 저장
    turn_number = len(session.get("conversation_history", [])) + 1
    session.setdefault("conversation_history", []).append({
        "turn": turn_number,
        "question": session["current_question"],
        "answer": body.answer,
        "answered_at": datetime.now().isoformat(),
    })

    # 첫 청크 분류를 위한 동기화 객체
    first_event = asyncio.Event()
    first_result: dict = {}
    queue: asyncio.Queue = asyncio.Queue()

    async def _stream_worker():
        """백그라운드에서 astream 소비 — 큐에 청크 적재"""
        got_first = False
        try:
            async for mode, chunk in graph.astream(
                Command(resume={"answer": body.answer}),
                config=config,
                stream_mode=["updates", "custom"],
            ):
                if not got_first:
                    if mode == "updates" and "__interrupt__" in chunk:
                        # 다음 질문 경로 → 기존 동작 유지
                        question = chunk["__interrupt__"][0].value.get("question")
                        first_result["type"] = "question"
                        first_result["question"] = question
                        got_first = True
                        first_event.set()
                        return  # 스트리밍 불필요

                    if mode == "updates" and (set(chunk.keys()) & ANALYSIS_NODES):
                        # 분석 시작 감지
                        first_result["type"] = "analyzing"
                        got_first = True
                        first_event.set()

                # 분석 경로인 경우 모든 청크를 큐에 적재
                if first_result.get("type") == "analyzing":
                    await queue.put((mode, chunk))

            # 스트림 정상 종료 sentinel
            await queue.put(None)

            # got_first가 False인 채로 종료된 경우 (예상치 못한 흐름)
            if not got_first:
                first_result["type"] = "analyzing"
                first_event.set()

        except Exception as e:
            logger.error(f"[스트림 워커 오류] session_id={session_id}, {e}")
            first_result.setdefault("type", "error")
            first_result["error"] = str(e)
            first_event.set()
            await queue.put(e)

    # 백그라운드 워커 시작 전에 큐를 세션에 저장
    session["_stream_queue"] = queue
    task = asyncio.create_task(_stream_worker())
    session["_stream_task"] = task

    try:
        await asyncio.wait_for(first_event.wait(), timeout=settings.llm_timeout_seconds)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="LLM 응답 시간 초과")

    result_type = first_result.get("type")

    if result_type == "question":
        session["current_question"] = first_result["question"]
        return AnswerResponse(
            session_id=session_id,
            question=first_result["question"],
            status="waiting",
        )
    elif result_type == "analyzing":
        session["status"] = "analyzing"
        logger.info(f"[분석시작] session_id={session_id}")
        return AnswerResponse(session_id=session_id, status="analyzing")
    else:
        raise HTTPException(
            status_code=500,
            detail=first_result.get("error", "분석 처리 중 오류가 발생했습니다."),
        )


@router.get("/{session_id}/stream")
async def stream_analysis_progress(session_id: str, request: Request):
    """
    [GET /sessions/{session_id}/stream] 분석 진행 상황 SSE 스트리밍

    - EventSource로 연결하면 분석 단계별 이벤트를 실시간으로 수신합니다.
    - 이벤트 종류: connected, node_progress, diagnosis_subtask, completed, error
    """
    store = get_session_store()
    if session_id not in store:
        raise SessionNotFoundError(session_id)

    session = store[session_id]
    graph = await get_graph(request)

    async def event_generator():
        yield _sse_event("connected", {"session_id": session_id})

        queue = session.get("_stream_queue")
        if queue is None:
            yield _sse_event("error", {"message": "스트림 큐가 없습니다. 먼저 답변을 제출하세요."})
            return

        while True:
            # 클라이언트 연결 해제 확인
            if await request.is_disconnected():
                logger.info(f"[SSE 연결 해제] session_id={session_id}")
                break

            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # 하트비트로 연결 유지
                yield _sse_heartbeat()
                continue

            # None sentinel: 스트림 정상 종료
            if item is None:
                graph_state = await graph.aget_state(session["graph_config"])

                # graph_state.next가 있으면 interrupt 대기 중 (추가 상담 필요)
                if graph_state.next:
                    question = None
                    for task in (graph_state.tasks or []):
                        for intr in (getattr(task, "interrupts", []) or []):
                            q = intr.value.get("question") if isinstance(intr.value, dict) else None
                            if q:
                                question = q
                                break
                        if question:
                            break
                    question = question or "증상에 대해 계속 답변해 주세요."

                    session["status"] = "patient response waiting"
                    session["current_question"] = question
                    logger.info(f"[상담재개] session_id={session_id}")
                    yield _sse_event("resumed", {"question": question})
                    break

                # 진짜 완료
                final_report = graph_state.values.get(
                    "diagnosis_research_result",
                    "진단 보고서가 생성되었습니다.",
                )
                session["status"] = "completed"
                session["final_report"] = final_report
                logger.info(f"[진단완료-SSE] session_id={session_id}")
                yield _sse_event("completed", {"has_report": bool(final_report)})
                break

            # 예외 객체: 오류 전파
            if isinstance(item, Exception):
                yield _sse_event("error", {"message": str(item)})
                break

            # 정상 청크 변환 후 전송
            mode, chunk = item
            for sse_str in _chunk_to_sse_events(mode, chunk):
                yield sse_str

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
        "current_question": session.get("current_question"),
        "patient_info": session["patient_info"],
        "has_report": session["final_report"] is not None,
    }
