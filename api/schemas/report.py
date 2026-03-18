from pydantic import BaseModel


class ReportResponse(BaseModel):
    """GET /sessions/{id}/report 응답 - 최종 진단 보고서"""
    session_id: str
    report: str    # 진단 보고서 내용 (마크다운 형식)
    status: str
