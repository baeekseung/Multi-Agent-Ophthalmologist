"""안과 임상 가이드라인 ChromaDB RAG 모듈.

data/guidelines/ 에 저장된 안과 임상 가이드라인 문서를 ChromaDB에 인덱싱하고
의미론적 유사도 검색을 제공합니다.

사용:
    from app.tools.guideline_rag import guideline_search_tool, ensure_guidelines_indexed
    await ensure_guidelines_indexed()  # 서버 시작 시 1회 호출
"""

import os
from functools import lru_cache

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from langchain_core.tools import InjectedToolCallId, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from typing_extensions import Annotated

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 가이드라인 문서 디렉토리 (프로젝트 루트 기준)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUIDELINES_DIR = os.path.join(_BASE_DIR, "data", "guidelines")
CHROMA_DB_PATH = os.path.join(_BASE_DIR, "data", "chroma_db")
COLLECTION_NAME = "ophthalmic_guidelines"

# 청크 설정
CHUNK_SIZE = 800      # 문자 기준
CHUNK_OVERLAP = 100


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """텍스트를 overlap 있는 청크로 분할합니다."""
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


@lru_cache(maxsize=1)
def _get_collection():
    """ChromaDB 컬렉션 싱글턴 반환."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

    embedding_fn = OpenAIEmbeddingFunction(
        api_key=api_key,
        model_name="text-embedding-3-small",
    )
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"description": "안과 임상 가이드라인 벡터 DB"},
    )
    return collection


def index_guidelines(force: bool = False) -> int:
    """data/guidelines/ 의 텍스트 파일을 ChromaDB에 인덱싱합니다.

    Args:
        force: True이면 기존 데이터를 삭제하고 재인덱싱

    Returns:
        인덱싱된 청크 수
    """
    collection = _get_collection()

    if not os.path.exists(GUIDELINES_DIR):
        logger.warning(f"[RAG] 가이드라인 디렉토리 없음: {GUIDELINES_DIR}")
        return 0

    # 기존 데이터 확인
    existing_count = collection.count()
    if existing_count > 0 and not force:
        logger.info(f"[RAG] 가이드라인 이미 인덱싱됨 ({existing_count}개 청크). 건너뜀.")
        return existing_count

    if force and existing_count > 0:
        # 기존 데이터 전체 삭제 후 재인덱싱
        all_ids = collection.get(include=[])["ids"]
        if all_ids:
            collection.delete(ids=all_ids)
        logger.info("[RAG] 기존 인덱스 삭제 후 재인덱싱 시작")

    txt_files = [f for f in os.listdir(GUIDELINES_DIR) if f.endswith(".txt")]
    if not txt_files:
        logger.warning(f"[RAG] {GUIDELINES_DIR} 에 .txt 파일 없음")
        return 0

    all_docs, all_ids, all_metas = [], [], []
    for fname in txt_files:
        fpath = os.path.join(GUIDELINES_DIR, fname)
        with open(fpath, encoding="utf-8") as f:
            content = f.read()

        disease_name = fname.replace(".txt", "")
        chunks = _chunk_text(content)
        for i, chunk in enumerate(chunks):
            all_docs.append(chunk)
            all_ids.append(f"{disease_name}_{i}")
            all_metas.append({"source": fname, "disease": disease_name, "chunk_index": i})

    # 배치 단위로 upsert (ChromaDB 권장: 최대 5000개)
    batch_size = 100
    total = 0
    for i in range(0, len(all_docs), batch_size):
        collection.upsert(
            documents=all_docs[i:i + batch_size],
            ids=all_ids[i:i + batch_size],
            metadatas=all_metas[i:i + batch_size],
        )
        total += len(all_docs[i:i + batch_size])

    logger.info(f"[RAG] 가이드라인 인덱싱 완료: {len(txt_files)}개 파일, {total}개 청크")
    return total


def ensure_guidelines_indexed() -> None:
    """가이드라인이 인덱싱되지 않은 경우 자동으로 인덱싱합니다."""
    try:
        collection = _get_collection()
        if collection.count() == 0:
            logger.info("[RAG] 가이드라인 미인덱싱 감지 → 자동 인덱싱 시작")
            count = index_guidelines()
            logger.info(f"[RAG] 자동 인덱싱 완료: {count}개 청크")
        else:
            logger.info(f"[RAG] 가이드라인 인덱스 확인 완료: {collection.count()}개 청크")
    except Exception as e:
        logger.error(f"[RAG] 가이드라인 인덱싱 오류: {e}")


def search_guidelines(query: str, n_results: int = 3) -> list[dict]:
    """안과 임상 가이드라인에서 의미 유사도 검색을 수행합니다.

    Args:
        query: 검색 쿼리 (증상, 질병명, 치료 방법 등)
        n_results: 반환할 최대 결과 수

    Returns:
        검색 결과 목록 (source, disease, content, distance)
    """
    collection = _get_collection()

    if collection.count() == 0:
        logger.warning("[RAG] 가이드라인 인덱스가 비어있음. ensure_guidelines_indexed()를 먼저 호출하세요.")
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    output = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        output.append({
            "source": meta.get("source", "unknown"),
            "disease": meta.get("disease", "unknown"),
            "content": doc,
            "relevance_score": round(1 - dist, 3),  # 코사인 유사도 (0~1)
        })

    return output


@tool(parse_docstring=True)
def guideline_search_tool(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    n_results: int = 3,
) -> Command:
    """안과 임상 가이드라인 벡터 DB에서 관련 정보를 검색합니다.

    웹 검색(tavily_search) 이전 또는 이후에 항상 이 도구를 사용하여
    AAO/TFOS/KOS 공식 가이드라인 기반의 근거 있는 정보를 확인하세요.

    Args:
        query: 검색할 임상 질문 (예: "안구건조증 2단계 치료", "녹내장 진단 기준")
        tool_call_id: 주입된 도구 호출 식별자
        n_results: 반환할 결과 수 (기본 3)

    Returns:
        가이드라인 검색 결과를 포함한 ToolMessage Command
    """
    logger.info(f"[TOOL] guideline_search_tool: '{query}' (n_results={n_results})")

    try:
        results = search_guidelines(query, n_results=n_results)
    except Exception as e:
        logger.error(f"[TOOL] guideline_search_tool 오류: {e}")
        error_msg = f"가이드라인 검색 중 오류 발생: {e}"
        return Command(update={"messages": [ToolMessage(error_msg, tool_call_id=tool_call_id)]})

    if not results:
        msg = f"'{query}'에 대한 가이드라인 검색 결과가 없습니다."
        return Command(update={"messages": [ToolMessage(msg, tool_call_id=tool_call_id)]})

    lines = [f"[안과 임상 가이드라인 검색 결과: '{query}']\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"## 결과 {i} (출처: {r['source']}, 관련도: {r['relevance_score']})\n"
            f"{r['content']}\n"
        )

    result_text = "\n".join(lines)
    logger.debug(f"[TOOL] guideline_search_tool {len(results)}건 반환 (관련도: {[r['relevance_score'] for r in results]})")

    return Command(update={"messages": [ToolMessage(result_text, tool_call_id=tool_call_id)]})
