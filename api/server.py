from contextlib import asynccontextmanager
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from app.prompts import INITIAL_CONSULTATION_MESSAGE

# LangGraph 그래프 인스턴스 (앱 시작 시 한 번만 빌드)
graph = None

# MemorySaver: 세션(thread_id)별 그래프 상태를 메모리에 저장하는 체크포인터
# 같은 thread_id로 graph.ainvoke를 여러 번 호출해도 상태가 유지됨
checkpointer = None

# 세션 정보 저장소: { session_id: { ... } }
sessions = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 앱 시작 시: 그래프 빌드
    FastAPI 앱 종료 시: 정리 작업

    @asynccontextmanager 데코레이터:
    - yield 이전 코드 → 앱 시작 시 실행
    - yield 이후 코드 → 앱 종료 시 실행
    """
    global graph, checkpointer

    # 앱 시작 시: LangGraph 그래프 빌드
    print("서버 시작 - Graph Bulid")
    from app.graph import build_graph

    # MemorySaver를 checkpointer로 주입하여 세션 간 상태 유지 가능하게 함
    checkpointer = MemorySaver()
    graph = await build_graph(checkpointer=checkpointer)
    print("Graph Bulid complete")

    yield  # ← 여기서 앱이 실행됨 (요청 처리)

    # 앱 종료 시: 필요한 정리 작업 추가 가능
    print("서버 종료")


app = FastAPI(
    title="AGENTIC-OPHTIMUS API",
    description="안과 AI 진료/진단 에이전트 RESTful API",
    version="1.0.0",
    lifespan=lifespan,  # 라이프사이클 함수 등록
)


# Pydantic 스키마 (요청/응답 데이터 모델)
# Pydantic: 데이터 검증 라이브러리. BaseModel을 상속받아 정의
# FastAPI가 요청 Body를 자동으로 파싱하고 Swagger 문서를 생성해줌

class SessionCreateRequest(BaseModel):
    """POST /sessions 요청 Body - 환자 기본 정보"""
    patient_name: str = "백승주"
    patient_age: int = 29
    patient_gender: str = "남자"


class SessionResponse(BaseModel):
    """POST /sessions 응답 - 세션 ID + 첫 번째 AI 질문"""
    session_id: str
    question: str       # AI가 환자에게 던지는 첫 번째 질문
    status: str         # "waiting": 답변 대기 중


class AnswerRequest(BaseModel):
    """POST /sessions/{id}/answer 요청 Body - 환자 답변"""
    answer: str


class AnswerResponse(BaseModel):
    """POST /sessions/{id}/answer 응답 - 다음 질문 or 완료"""
    session_id: str
    question: Optional[str] = None   # 다음 질문 (완료 시 None)
    status: str                      # "waiting" | "completed"
    message: Optional[str] = None    # 완료 시 안내 메시지


class ReportResponse(BaseModel):
    """GET /sessions/{id}/report 응답 - 최종 진단 보고서"""
    session_id: str
    report: str    # 진단 보고서 내용 (마크다운 형식)
    status: str


# 유틸리티 함수
def extract_question(result: dict) -> Optional[str]:
    """
    LangGraph 실행 결과에서 interrupt 질문을 추출합니다.

    LangGraph에서 interrupt()가 호출되면:
    result["__interrupt__"] = [Interrupt(value={"question": "..."})]
    형태로 반환됩니다.
    """
    interrupts = result.get("__interrupt__", [])
    if interrupts:
        # 첫 번째 interrupt에서 "question" 키 추출
        return interrupts[0].value.get("question", "질문을 가져올 수 없습니다.")
    return None  # interrupt 없으면 None (그래프 완료)

# 엔드포인트 정의
@app.get("/")
async def root_function():
    return {
        "status": "ok",
        "graph_ready": graph is not None,
        "active_sessions": len(sessions),
    }

# 엔드포인트 정의
@app.get("/health")
async def health_check():
    """
    [GET /health] 서버 상태 확인

    서버가 정상 작동 중인지, 그래프가 준비되었는지 확인합니다.
    """
    return {
        "status": "ok",
        "graph_ready": graph is not None,
        "active_sessions": len(sessions),
    }


@app.post("/sessions", response_model=SessionResponse)
async def start_consiltation(request: SessionCreateRequest):
    """
    [POST /sessions] 새 진료 세션 생성

    동작 순서:
    1. UUID로 고유한 session_id 생성
    2. LangGraph 그래프 실행 시작
       - consultation_agent: AI가 첫 번째 진료 질문 생성
       - patient_response: interrupt() 호출 → 그래프 일시 중지
    3. interrupt에서 질문 추출 → 응답 반환
    """
    # 1. 고유 세션 ID 생성 (UUID4: 랜덤 고유값)
    session_id = str(uuid4())

    # 2. LangGraph config 설정
    # thread_id: 세션을 구분하는 키. 같은 thread_id로 ainvoke하면 이전 상태 이어서 실행
    config = {"configurable": {"thread_id": session_id}}

    # 3. 초기 입력 상태 (main.py와 동일한 방식)
    initial_input = {
        "messages": [HumanMessage(
            content=f"## previous_consultation_summary: 아직 진료상담 이력이 없습니다.\n\n## expert_opinion: {INITIAL_CONSULTATION_MESSAGE}",
            name="expert",
        )],
        "consultation_turn": 1, # 진료 턴 카운터 초기화
    }

    try:
        result = await graph.ainvoke(initial_input, config=config)

        # interrupt에서 질문 추출
        question = extract_question(result)

        if question is None:
            # interrupt 없이 완료된 경우 (예외 상황)
            raise HTTPException(status_code=500, detail="첫 번째 질문을 가져오지 못했습니다.")

        # 6. 세션 정보 저장
        sessions[session_id] = {
            "session_id": session_id,
            "status": "patient response waiting",   # 답변 대기 중
            "current_question": question,   # 현재 AI 질문
            "final_report": None,           # 아직 보고서 없음
            "graph_config": config,         # 그래프 재개에 필요한 설정
            "patient_info": {
                "name": request.patient_name,
                "age": request.patient_age,
                "gender": request.patient_gender,
            },
        }

        return SessionResponse(
            session_id=session_id,
            question=question,
            status="waiting",
        )

    except HTTPException:
        raise  # FastAPI HTTPException은 그대로 재발생
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"세션 생성 오류: {str(e)}")


@app.post("/sessions/{session_id}/answer", response_model=AnswerResponse)
async def submit_patient_answer(session_id: str, request: AnswerRequest):
    """
    [POST /sessions/{session_id}/answer] 환자 답변 제출

    동작 순서:
    1. 세션 ID로 저장된 graph_config 조회
    2. Command(resume=answer)로 interrupt된 그래프 재개
    3. 결과 확인:
       - 다음 interrupt → 다음 질문 반환 (status: "waiting")
       - interrupt 없음 → 그래프 완료 → 보고서 저장 (status: "completed")
    """
    # 세션 존재 여부 확인
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    session = sessions[session_id]

    # 이미 완료된 세션은 거부
    if session["status"] == "completed":
        raise HTTPException(status_code=400, detail="이미 완료된 세션입니다.")

    config = session["graph_config"]

    try:
        # Command(resume=...): interrupt로 중지된 그래프를 재개하는 LangGraph 명령
        # patient_response.py에서 user_input = interrupt(...)의 반환값으로 {"answer": "..."}가 전달됨
        result = await graph.ainvoke(
            Command(resume={"answer": request.answer}),
            config=config,
        )

        # 다음 질문 여부 확인
        next_question = extract_question(result)

        if next_question:
            # 아직 상담이 끝나지 않음 → 다음 질문 반환
            session["current_question"] = next_question
            return AnswerResponse(
                session_id=session_id,
                question=next_question,
                status="waiting",
            )
        else:
            # 그래프 완료 → 최종 상태에서 보고서 추출
            # graph.aget_state(): 특정 thread_id의 현재 상태를 가져옴
            graph_state = await graph.aget_state(config)
            final_report = graph_state.values.get(
                "diagnosis_research_result",
                "진단 보고서가 생성되었습니다."
            )

            # 세션 상태 업데이트
            session["status"] = "completed"
            session["final_report"] = final_report

            return AnswerResponse(
                session_id=session_id,
                status="completed",
                message=f"진단이 완료되었습니다. GET /sessions/{session_id}/report 에서 보고서를 확인하세요.",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"답변 처리 오류: {str(e)}")


@app.get("/sessions/{session_id}/status")
async def get_session_status(session_id: str):
    """
    [GET /sessions/{session_id}/status] 세션 현재 상태 조회

    세션 ID에 해당하는 현재 상태 정보를 반환합니다.
    보고서 전체 내용은 /report 엔드포인트를 이용하세요.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    session = sessions[session_id]
    return {
        "session_id": session["session_id"],
        "status": session["status"],
        "current_question": session["current_question"],
        "patient_info": session["patient_info"],
        "has_report": session["final_report"] is not None,
    }


@app.get("/sessions/{session_id}/report", response_model=ReportResponse)
async def get_report(session_id: str):
    """
    [GET /sessions/{session_id}/report] 최종 진단 보고서 조회

    status가 "completed"인 경우에만 보고서를 반환합니다.
    아직 진단이 완료되지 않은 경우 400 에러를 반환합니다.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    session = sessions[session_id]

    # 미완료 세션은 보고서 없음
    if session["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"진단이 아직 완료되지 않았습니다. 현재 상태: {session['status']}",
        )

    if not session["final_report"]:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    return ReportResponse(
        session_id=session_id,
        report=session["final_report"],
        status="completed",
    )
