"""
utils/embeddings.py — Ollama 임베딩 유틸
OpenAI 클라이언트 대신 Ollama REST API를 직접 호출합니다.
모델: qwen3-embedding:4b (2560차원, 다국어 MTEB 1위)
"""
import httpx

from config import EMBED_MODEL, OLLAMA_BASE_URL

# Ollama 임베딩 엔드포인트
_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embed"

# 싱글턴 httpx 클라이언트 (커넥션 재사용)
_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """싱글턴 httpx 클라이언트 반환."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=120.0)
    return _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    텍스트 리스트 → 임베딩 벡터 리스트.
    Ollama /api/embed 엔드포인트 사용 (배치 처리 지원).
    """
    client = get_http_client()
    response = await client.post(
        _EMBED_URL,
        json={
            "model": EMBED_MODEL,
            "input": texts,   # 배치 입력 지원
        },
    )
    response.raise_for_status()
    data = response.json()
    # Ollama 응답 형식: {"embeddings": [[...], [...]]}
    return data["embeddings"]


async def close_http_client() -> None:
    """앱 종료 시 클라이언트 정리."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None