from typing import Optional

from pydantic import BaseModel


class SessionResponse(BaseModel):
    """POST /sessions 응답 - 세션 ID + 첫 번째 AI 질문"""
    session_id: str
    question: str    # AI가 환자에게 던지는 첫 번째 질문
    status: str      # "waiting": 답변 대기 중


class AnswerRequest(BaseModel):
    """POST /sessions/{id}/answer 요청 Body - 환자 답변"""
    answer: str


class AnswerResponse(BaseModel):
    """POST /sessions/{id}/answer 응답 - 다음 질문 or 완료"""
    session_id: str
    question: Optional[str] = None   # 다음 질문 (완료 시 None)
    status: str                      # "waiting" | "completed"
    message: Optional[str] = None    # 완료 시 안내 메시지


class ConversationTurn(BaseModel):
    """대화 1턴: 질문 + 답변 쌍"""
    turn: int
    question: str
    answer: str
    answered_at: str  # ISO 8601


class ConversationHistoryResponse(BaseModel):
    """GET /sessions/{id}/conversation 응답"""
    session_id: str
    status: str
    total_turns: int
    conversation: list[ConversationTurn]
