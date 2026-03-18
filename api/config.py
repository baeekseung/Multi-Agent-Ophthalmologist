from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str
    database_url: str
    tavily_api_key: str = ""

    # CORS 허용 오리진
    # .env에서 JSON 배열 형태로 설정: CORS_ORIGINS='["http://localhost:3000","http://localhost:5173"]'
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # 세션 TTL (시간 단위, 기본 1시간)
    session_ttl_hours: int = 1

    # LLM 응답 타임아웃 (초 단위, 기본 120초)
    llm_timeout_seconds: int = 120

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
