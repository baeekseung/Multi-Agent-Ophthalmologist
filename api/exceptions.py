from fastapi import Request
from fastapi.responses import JSONResponse


# 커스텀 예외 클래스 계층 구조
class OphtimusAPIError(Exception):
    """AGENTIC-OPHTIMUS API 기본 예외"""
    pass


class SessionNotFoundError(OphtimusAPIError):
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"세션을 찾을 수 없습니다: {session_id}")


class SessionAlreadyCompletedError(OphtimusAPIError):
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"이미 완료된 세션입니다: {session_id}")


class SessionNotCompletedError(OphtimusAPIError):
    def __init__(self, session_id: str, current_status: str):
        self.session_id = session_id
        self.current_status = current_status
        super().__init__(f"진단이 아직 완료되지 않았습니다. 현재 상태: {current_status}")


class GraphNotReadyError(OphtimusAPIError):
    def __init__(self):
        super().__init__("LangGraph 그래프가 준비되지 않았습니다.")


def register_exception_handlers(app) -> None:
    """전역 예외 핸들러를 FastAPI 앱에 등록합니다."""

    @app.exception_handler(SessionNotFoundError)
    async def session_not_found_handler(request: Request, exc: SessionNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": "SESSION_NOT_FOUND", "message": str(exc)},
        )

    @app.exception_handler(SessionAlreadyCompletedError)
    async def session_completed_handler(request: Request, exc: SessionAlreadyCompletedError):
        return JSONResponse(
            status_code=400,
            content={"error": "SESSION_ALREADY_COMPLETED", "message": str(exc)},
        )

    @app.exception_handler(SessionNotCompletedError)
    async def session_not_completed_handler(request: Request, exc: SessionNotCompletedError):
        return JSONResponse(
            status_code=400,
            content={"error": "SESSION_NOT_COMPLETED", "message": str(exc)},
        )

    @app.exception_handler(GraphNotReadyError)
    async def graph_not_ready_handler(request: Request, exc: GraphNotReadyError):
        return JSONResponse(
            status_code=503,
            content={"error": "GRAPH_NOT_READY", "message": str(exc)},
        )
