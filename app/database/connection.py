import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.utils.logger import get_logger

logger = get_logger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Base(DeclarativeBase):
    pass

def init_db() -> None:
    """테이블이 없으면 생성한다."""
    try:
        from app.database.models import PatientRecord  # 순환 임포트 방지
        Base.metadata.create_all(bind=engine)
        logger.info("[DB] 테이블 생성/확인 완료")
    except Exception as e:
        logger.error(f"[DB] 테이블 생성 실패: {e}")
        raise
