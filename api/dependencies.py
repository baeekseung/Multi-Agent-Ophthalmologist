from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import Request

from api.exceptions import GraphNotReadyError

# 전역 세션 저장소: { session_id: { ... } }
_sessions: Dict[str, Any] = {}


def get_session_store() -> Dict[str, Any]:
    return _sessions


async def get_graph(request: Request):
    """앱 상태에서 LangGraph 인스턴스 반환"""
    graph = getattr(request.app.state, "graph", None)
    if graph is None:
        raise GraphNotReadyError()
    return graph


async def cleanup_expired_sessions(ttl_hours: int = 1) -> int:
    """만료된 세션을 정리하고 삭제된 세션 수를 반환합니다."""
    cutoff = datetime.now() - timedelta(hours=ttl_hours)
    expired = [
        k for k, v in _sessions.items()
        if v.get("created_at") and v["created_at"] < cutoff
    ]
    for k in expired:
        del _sessions[k]
    return len(expired)
