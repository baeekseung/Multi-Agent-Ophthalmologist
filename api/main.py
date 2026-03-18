import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.memory import MemorySaver

from api.config import settings
from api.dependencies import cleanup_expired_sessions
from api.exceptions import register_exception_handlers
from api.middleware.logging import RequestLoggingMiddleware
from api.routers import health, reports, sessions
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def _periodic_cleanup():
    """만료된 세션을 주기적으로 정리합니다 (1시간 간격)."""
    while True:
        await asyncio.sleep(3600)
        count = await cleanup_expired_sessions(settings.session_ttl_hours)
        if count > 0:
            logger.info(f"[세션정리] 만료된 세션 {count}개 삭제 (TTL={settings.session_ttl_hours}h)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작: 그래프 빌드 + 백그라운드 정리 태스크 시작
    logger.info("서버 시작 - Graph Build")
    from app.graph import build_graph

    app.state.checkpointer = MemorySaver()
    app.state.graph = await build_graph(checkpointer=app.state.checkpointer)
    logger.info("Graph Build 완료")

    cleanup_task = asyncio.create_task(_periodic_cleanup())

    yield  # 앱 실행

    # 앱 종료: 백그라운드 태스크 취소
    cleanup_task.cancel()
    logger.info("서버 종료")


app = FastAPI(
    title="AGENTIC-OPHTIMUS API",
    description="안과 AI 진료/진단 에이전트 RESTful API",
    version="1.0.0",
    lifespan=lifespan,
)

# 미들웨어 등록 (등록 역순으로 실행: 로깅 → CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

# 전역 예외 핸들러 등록
register_exception_handlers(app)

# 라우터 등록
app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(reports.router)

# Static 파일 서빙
_static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir, html=True), name="static")


@app.get("/", include_in_schema=False)
async def root():
    """루트 접근 시 프론트엔드 SPA로 리다이렉트."""
    return RedirectResponse(url="/static/index.html")
