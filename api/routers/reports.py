from fastapi import APIRouter, HTTPException

from api.dependencies import get_session_store
from api.exceptions import SessionNotCompletedError, SessionNotFoundError
from api.schemas.report import ReportResponse

router = APIRouter(prefix="/sessions", tags=["보고서"])


@router.get("/{session_id}/report", response_model=ReportResponse)
async def get_report(session_id: str):
    """
    [GET /sessions/{session_id}/report] 최종 진단 보고서 조회

    status가 "completed"인 경우에만 보고서를 반환합니다.
    """
    store = get_session_store()
    if session_id not in store:
        raise SessionNotFoundError(session_id)

    session = store[session_id]
    if session["status"] != "completed":
        raise SessionNotCompletedError(session_id, session["status"])

    if not session["final_report"]:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    return ReportResponse(
        session_id=session_id,
        report=session["final_report"],
        status="completed",
    )
