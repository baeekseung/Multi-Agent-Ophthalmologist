import time
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.logger import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """HTTP 요청/응답을 자동으로 로깅하는 미들웨어.

    - 요청마다 고유한 X-Request-ID 헤더를 생성 및 전파
    - 처리 시간 측정 후 로그 기록
    """

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid4())[:8]
        request.state.request_id = request_id

        start = time.time()
        try:
            response = await call_next(request)
            elapsed = time.time() - start

            logger.info(
                f"[{request_id}] {request.method} {request.url.path} "
                f"→ {response.status_code} ({elapsed:.3f}s)"
            )
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as exc:
            elapsed = time.time() - start
            logger.error(
                f"[{request_id}] {request.method} {request.url.path} "
                f"→ ERROR ({elapsed:.3f}s): {exc}"
            )
            raise
