"""
services/upload_service.py — PDF 업로드 및 벡터 저장 비즈니스 로직
PDF 파싱 → AI 분류 → 청크 분할 → 임베딩 → pgvector 저장 파이프라인.
OpenAI → Ollama (qwen3.5:35b-a3b) 로 변경.
"""
import json
import logging
import time

import httpx
from fastapi import HTTPException

from config import CHAT_MODEL, OLLAMA_BASE_URL
from app.database import get_pool
from app.utils.embeddings import embed_texts
from app.utils.pdf import extract_text_from_pdf, split_into_chunks

logger = logging.getLogger(__name__)

_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"


async def classify_document(source: str, preview: str) -> dict:
    
    # 1. 파일명 패턴으로 우선 분류 (AI 호출 없이 빠르게 처리)
    FILENAME_CATEGORY = {
        "(법률)":    "법령",
        "(대통령령)": "시행령",
        "(부령)":    "시행규칙",
        "(훈령)":    "집행기준",
        "(고시)":    "집행기준",
    }
    FILENAME_LAW = {
        "소득세법":         "소득세법",
        "부가가치세법":     "부가가치세법",
        "법인세법":         "법인세법",
        "상속세및증여세법": "상속세및증여세법",
        "지방세법":         "지방세법",
        "조세특례제한법":   "조세특례제한법",
        "국세기본법":       "국세기본법",
    }

    detected_category = next(
        (v for k, v in FILENAME_CATEGORY.items() if k in source), None
    )
    detected_law = next(
        (v for k, v in FILENAME_LAW.items() if k in source), None
    )

    # 파일명에서 둘 다 감지되면 AI 호출 없이 바로 반환
    if detected_category and detected_law:
        return {"category": detected_category, "law_name": detected_law}

    # 2. 파일명으로 못 잡은 경우만 AI로 분류
    prompt = (
        "대한민국 세무 문서를 분석하여 JSON으로만 응답하세요.\n\n"
        "category 후보: 법령, 시행령, 시행규칙, 집행기준, 기타\n"
        "파일명 패턴 참고:\n"
        "  - '(법률)' 포함    → category: 법령\n"
        "  - '(대통령령)' 포함 → category: 시행령\n"
        "  - '(부령)' 포함    → category: 시행규칙\n"
        "  - '(훈령)','(고시)' 포함 → category: 집행기준\n\n"
        "law_name 후보: 소득세법, 부가가치세법, 법인세법, 상속세및증여세법, "
        "지방세법, 조세특례제한법, 국세기본법, 공통\n\n"
        "법령 위계 우선순위: 법령 > 시행령 > 시행규칙 > 집행기준\n\n"
        f"파일명: {source}\n"
        f"내용 도입부: {preview[:800]}\n\n"
        '출력 예시: {"category": "법령", "law_name": "소득세법"}\n'
        "오직 JSON만 출력하세요. 다른 텍스트는 절대 포함하지 마세요."
    )
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                _CHAT_URL,
                json={
                    "model": CHAT_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 100,
                    },
                },
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            result = json.loads(content)
            
            # 파일명에서 부분적으로 감지된 값으로 보완
            if detected_category:
                result["category"] = detected_category
            if detected_law:
                result["law_name"] = detected_law
                
            return result
    except Exception:
        return {
            "category": detected_category or "기타",
            "law_name": detected_law or "공통",
        }


async def process_upload(
    file_bytes: bytes,
    filename: str,
    uploader_email: str,
) -> dict:
    """업로드 파이프라인: PDF 파싱 → AI 분류 → 청크 분할 → 임베딩 → DB 저장."""
    t0 = time.perf_counter()
    logger.info("[UPLOAD] 시작: %s (%.1fKB) | 업로더: %s",
                filename, len(file_bytes) / 1024, uploader_email)

    # 1. PDF 파싱
    try:
        full_text = extract_text_from_pdf(file_bytes)
    except Exception as e:
        logger.error("[UPLOAD] PDF 파싱 실패: %s — %s", filename, e)
        raise HTTPException(status_code=422, detail=f"PDF 파싱 오류: {e}")

    if not full_text.strip():
        logger.warning("[UPLOAD] 텍스트 추출 불가 (스캔 PDF): %s", filename)
        raise HTTPException(
            status_code=422,
            detail="텍스트를 추출할 수 없습니다. (스캔 PDF 미지원)",
        )
    logger.info("[UPLOAD] PDF 파싱 완료: %d자", len(full_text))

    # 2. AI 분류
    meta = await classify_document(filename, full_text)
    logger.info("[UPLOAD] 문서 분류: category=%s | law_name=%s",
                meta.get("category"), meta.get("law_name"))

    metadata_base = {
        "source":   filename,
        "law_name": meta.get("law_name", "공통"),
        "category": meta.get("category", "기타"),
        "uploader": uploader_email,
    }

    # 3. 청크 분할
    chunks = split_into_chunks(full_text)
    logger.info("[UPLOAD] 청크 분할: %d개", len(chunks))

    # 4. 임베딩 (100개 배치)
    t1 = time.perf_counter()
    embeddings: list[list[float]] = []
    for i in range(0, len(chunks), 100):
        batch_end = min(i + 100, len(chunks))
        logger.info("[UPLOAD] 임베딩 중 %d~%d / %d ...", i + 1, batch_end, len(chunks))
        embeddings.extend(await embed_texts(chunks[i:batch_end]))
    logger.info("[UPLOAD] 임베딩 완료 (%.1fs)", time.perf_counter() - t1)

    # 5. DB 저장
    pool = await get_pool()
    async with pool.acquire() as conn:
        deleted = await conn.fetchval(
            "SELECT COUNT(*) FROM documents WHERE metadata->>'source' = $1", filename
        )
        if deleted:
            await conn.execute(
                "DELETE FROM documents WHERE metadata->>'source' = $1", filename
            )
            logger.info("[UPLOAD] 기존 청크 %d개 삭제 (덮어쓰기)", deleted)

        await conn.executemany(
            "INSERT INTO documents (content, embedding, metadata) VALUES ($1, $2, $3)",
            [
                (chunk, emb, json.dumps({**metadata_base, "chunk_index": idx}))
                for idx, (chunk, emb) in enumerate(zip(chunks, embeddings))
            ],
        )

    logger.info("[UPLOAD] 완료 — %d청크 저장 | 총 %.1fs", len(chunks), time.perf_counter() - t0)
    return {
        "status":        "ok",
        "filename":      filename,
        "law_name":      meta.get("law_name"),
        "category":      meta.get("category"),
        "chunks_stored": len(chunks),
    }