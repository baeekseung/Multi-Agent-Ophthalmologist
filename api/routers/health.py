from fastapi import APIRouter, Request

from api.dependencies import get_session_store

router = APIRouter(tags=["헬스체크"])


@router.get("/health")
async def health_check(request: Request):
    """서버 및 그래프 상태를 확인합니다."""
    store = get_session_store()
    return {
        "status": "ok",
        "graph_ready": getattr(request.app.state, "graph", None) is not None,
        "active_sessions": len(store),
    }
