"""환자 증례 벡터 유사도 검색 모듈.

진료 기록 저장 시 증상 설명을 임베딩하여 ChromaDB에 저장하고,
신규 환자 증상과 의미론적으로 유사한 과거 증례를 검색합니다.

기존 PostgreSQL ILIKE 검색을 보완하며, 증상 의미 유사도 기반으로
이름/나이/성별 조건 없이도 관련 증례를 찾을 수 있습니다.
"""

import os
from functools import lru_cache

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from app.utils.logger import get_logger

logger = get_logger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHROMA_DB_PATH = os.path.join(_BASE_DIR, "data", "chroma_db")
PATIENT_COLLECTION_NAME = "patient_cases"


@lru_cache(maxsize=1)
def _get_patient_collection():
    """환자 증례 ChromaDB 컬렉션 싱글턴 반환."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

    embedding_fn = OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name="text-embedding-3-small",
    )
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_or_create_collection(
        name=PATIENT_COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"description": "안과 환자 증례 벡터 DB"},
    )
    return collection


def add_patient_case(
    record_id: int,
    patient_name: str,
    patient_age: int,
    patient_gender: str,
    consultation_summary: str,
    final_report: str,
) -> None:
    """신규 환자 기록을 벡터 DB에 추가합니다.

    consultation_summary를 임베딩하여 유사 증례 검색의 기반으로 사용합니다.

    Args:
        record_id: PostgreSQL PatientRecord.id (고유 식별자)
        patient_name: 환자 이름
        patient_age: 환자 나이
        patient_gender: 환자 성별
        consultation_summary: 진료 상담 요약 (임베딩 대상)
        final_report: 최종 진단 보고서 내용
    """
    try:
        collection = _get_patient_collection()
        doc_id = f"patient_{record_id}"

        # 임베딩 대상: 상담 요약 + 최종 진단 핵심 (처음 500자)
        embed_text = f"{consultation_summary}\n\n[진단 요약]\n{final_report[:500]}"

        collection.upsert(
            documents=[embed_text],
            ids=[doc_id],
            metadatas=[{
                "record_id": record_id,
                "patient_name": patient_name,
                "patient_age": patient_age,
                "patient_gender": patient_gender,
                "consultation_summary": consultation_summary[:1000],
                "final_report_preview": final_report[:500],
            }],
        )
        logger.info(f"[PatientVec] 환자 기록 임베딩 저장: record_id={record_id}, 이름={patient_name}")
    except Exception as e:
        logger.error(f"[PatientVec] 환자 기록 임베딩 저장 실패: {e}")


def search_similar_cases(
    symptom_description: str,
    n_results: int = 3,
    min_relevance: float = 0.3,
) -> list[dict]:
    """증상 설명과 의미적으로 유사한 과거 환자 증례를 검색합니다.

    Args:
        symptom_description: 현재 환자의 증상 설명 (자유 텍스트)
        n_results: 반환할 최대 결과 수
        min_relevance: 최소 유사도 임계값 (0~1)

    Returns:
        유사 증례 목록 (patient_name, patient_age, consultation_summary, relevance_score)
    """
    try:
        collection = _get_patient_collection()
        total = collection.count()

        if total == 0:
            logger.info("[PatientVec] 저장된 환자 증례 없음")
            return []

        results = collection.query(
            query_texts=[symptom_description],
            n_results=min(n_results, total),
            include=["documents", "metadatas", "distances"],
        )

        output = []
        for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
            relevance = round(1 - dist, 3)
            if relevance < min_relevance:
                continue
            output.append({
                "record_id": meta.get("record_id"),
                "patient_name": meta.get("patient_name", "미상"),
                "patient_age": meta.get("patient_age", 0),
                "patient_gender": meta.get("patient_gender", "미상"),
                "consultation_summary": meta.get("consultation_summary", ""),
                "final_report_preview": meta.get("final_report_preview", ""),
                "relevance_score": relevance,
            })

        logger.info(f"[PatientVec] 유사 증례 검색: {len(output)}건 반환 (쿼리: {symptom_description[:80]}...)")
        return output

    except Exception as e:
        logger.error(f"[PatientVec] 유사 증례 검색 실패: {e}")
        return []
