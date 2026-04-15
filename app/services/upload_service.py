"""
services/upload_service.py — PDF 업로드 및 벡터 저장 비즈니스 로직
PDF 파싱 → AI 분류 → 청크 분할 → 임베딩 → pgvector 저장 파이프라인.
OpenAI → Ollama (qwen3.5:35b-a3b) 로 변경.
"""
import json

import httpx
from fastapi import HTTPException

from config import CHAT_MODEL, OLLAMA_BASE_URL
from app.database import get_pool
from app.utils.embeddings import embed_texts
from app.utils.pdf import extract_text_from_pdf, split_into_chunks

_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"


async def classify_document(source: str, preview: str) -> dict:
    """
    Ollama(qwen3.5)로 세무 문서 카테고리·세목 자동 분류.
    반환 예: {"category": "법령", "law_name": "소득세법"}
    """
    prompt = (
        "대한민국 세무 문서를 분석하여 JSON으로만 응답하세요.\n"
        "category 후보: 법령, 시행령, 시행규칙, 집행기준, 기타\n"
        "law_name 후보: 소득세법, 부가가치세법, 법인세법, 상속세및증여세법, "
        "지방세법, 조세특례제한법, 국세기본법, 공통\n"
        f"파일명: {source}\n"
        f"내용 도입부: {preview[:800]}\n"
        '출력 예시: {"category": "법령", "law_name": "소득세법"}\n'
        "오직 JSON만 출력하세요. 다른 텍스트는 절대 포함하지 마세요."
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _CHAT_URL,
                json={
                    "model": CHAT_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",   # Ollama JSON 모드
                    "options": {
                        "temperature": 0.0,  # 분류는 결정적으로
                        "num_predict": 100,
                    },
                },
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            return json.loads(content)
    except Exception:
        return {"category": "기타", "law_name": "공통"}


async def process_upload(
    file_bytes: bytes,
    filename: str,
    uploader_email: str,
) -> dict:
    """
    업로드 파이프라인 전체 실행.
    1. PDF 파싱
    2. AI 분류 (Ollama)
    3. 청크 분할
    4. 임베딩 (Ollama, 배치 100개)
    5. pgvector 저장 (기존 동일 파일 덮어쓰기)
    """
    # 1. PDF 파싱
    try:
        full_text = extract_text_from_pdf(file_bytes)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"PDF 파싱 오류: {e}")

    if not full_text.strip():
        raise HTTPException(
            status_code=422,
            detail="텍스트를 추출할 수 없습니다. (스캔 PDF 미지원)",
        )

    # 2. AI 분류
    meta = await classify_document(filename, full_text)
    metadata_base = {
        "source":   filename,
        "law_name": meta.get("law_name", "공통"),
        "category": meta.get("category", "기타"),
        "uploader": uploader_email,
    }

    # 3. 청크 분할
    chunks = split_into_chunks(full_text)

    # 4. 임베딩 (100개 배치)
    embeddings: list[list[float]] = []
    for i in range(0, len(chunks), 100):
        embeddings.extend(await embed_texts(chunks[i : i + 100]))

    # 5. DB 저장
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM documents WHERE metadata->>'source' = $1",
            filename,
        )
        await conn.executemany(
            "INSERT INTO documents (content, embedding, metadata) VALUES ($1, $2, $3)",
            [
                (
                    chunk,
                    emb,
                    json.dumps({**metadata_base, "chunk_index": idx}),
                )
                for idx, (chunk, emb) in enumerate(zip(chunks, embeddings))
            ],
        )

    return {
        "status":        "ok",
        "filename":      filename,
        "law_name":      meta.get("law_name"),
        "category":      meta.get("category"),
        "chunks_stored": len(chunks),
    }