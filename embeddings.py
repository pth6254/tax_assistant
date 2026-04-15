"""
utils/embeddings.py — OpenAI 임베딩 유틸
openai_client는 services 레이어에서 주입받지 않고
여기서 싱글턴으로 관리합니다.
"""
from openai import AsyncOpenAI

from app.config import EMBED_MODEL, OPENAI_API_KEY

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """싱글턴 OpenAI 클라이언트 반환."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """텍스트 리스트 → 임베딩 벡터 리스트 (배치 처리)."""
    client = get_openai_client()
    resp   = await client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in resp.data]
