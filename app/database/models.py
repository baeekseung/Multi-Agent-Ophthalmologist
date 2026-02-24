from datetime import datetime
from sqlalchemy import String, Text, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database.connection import Base

class PatientRecord(Base):
    __tablename__ = "patient_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_name: Mapped[str] = mapped_column(String(100), nullable=False)
    patient_age: Mapped[int] = mapped_column(Integer, nullable=False)
    patient_gender: Mapped[str] = mapped_column(String(10), nullable=False)
    consultation_summary: Mapped[str] = mapped_column(Text, nullable=False)
    final_report: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
