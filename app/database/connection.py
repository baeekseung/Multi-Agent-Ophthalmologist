import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Base(DeclarativeBase):
    pass

def init_db() -> None:
    """테이블이 없으면 생성한다."""
    from app.database.models import PatientRecord  # 순환 임포트 방지
    Base.metadata.create_all(bind=engine)
