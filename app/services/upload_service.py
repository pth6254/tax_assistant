"""User document upload, extraction, embedding, listing, and deletion."""
import asyncio
import json
from hashlib import sha256
import logging
import time
import uuid as _uuid

from fastapi import HTTPException

from app.database import get_pool
from config import EMBEDDING_VERSION
from app.services.document.structured_chunker import chunk_document
from app.services.document.extractors import extract_document, ExtractionError, OCRUnavailable
from app.services.embedding_service import embed_texts_for_storage
from app.services.llm_client import call_llm

logger = logging.getLogger(__name__)


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
        "상속세및증여세법": "상속세 및 증여세법",
        "상속세 및 증여세법": "상속세 및 증여세법",
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
        "law_name 후보: 소득세법, 부가가치세법, 법인세법, 상속세 및 증여세법, "
        "지방세법, 조세특례제한법, 국세기본법, 공통\n\n"
        "법령 위계 우선순위: 법령 > 시행령 > 시행규칙 > 집행기준\n\n"
        f"파일명: {source}\n"
        f"내용 도입부: {preview[:800]}\n\n"
        '출력 예시: {"category": "법령", "law_name": "소득세법"}\n'
        "오직 JSON만 출력하세요. 다른 텍스트는 절대 포함하지 마세요."
    )
    try:
        content = await call_llm(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100,
            purpose="document_classification",
        )
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
    user_id: str,
    uploader_email: str,
) -> dict:
    """Extract supported formats, classify, embed, then atomically replace stored chunks."""
    t0 = time.perf_counter()
    logger.info("[UPLOAD] 시작: %s (%.1fKB) | 업로더: %s",
                filename, len(file_bytes) / 1024, uploader_email)

    # OCR and ZIP/XML parsing are blocking; keep them off the event loop.
    try:
        extracted = await asyncio.to_thread(extract_document, file_bytes, filename)
    except OCRUnavailable as exc:
        logger.error("[UPLOAD] OCR 사용 불가: %s — %s", filename, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ExtractionError as exc:
        logger.warning("[UPLOAD] 문서 추출 실패: %s — %s", filename, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    full_text = extracted.text
    logger.info("[UPLOAD] %s 추출 완료: %d자 (OCR %d쪽)",
                extracted.format, len(full_text), extracted.ocr_pages)

    # 2. AI 분류
    meta = await classify_document(filename, full_text)
    logger.info("[UPLOAD] 문서 분류: category=%s | law_name=%s",
                meta.get("category"), meta.get("law_name"))

    metadata_base = {
        "source":   filename,
        "law_name": meta.get("law_name", "공통"),
        "category": meta.get("category", "기타"),
        "uploader": uploader_email,
        "format": extracted.format,
        "extraction_method": extracted.extraction_method,
        "ocr_pages": extracted.ocr_pages,
        "chunking_version": 2,
    }

    # 3. 청크 분할
    structured_chunks = chunk_document(extracted)
    chunks = [chunk.text for chunk in structured_chunks]
    logger.info("[UPLOAD] 청크 분할: %d개", len(chunks))

    # 4. 임베딩 (100개 배치)
    t1 = time.perf_counter()
    embeddings: list[list[float]] = []
    embeddings_v2: list[list[float]] = []
    for i in range(0, len(chunks), 100):
        batch_end = min(i + 100, len(chunks))
        logger.info("[UPLOAD] 임베딩 중 %d~%d / %d ...", i + 1, batch_end, len(chunks))
        batch_v1, batch_v2 = await embed_texts_for_storage(chunks[i:batch_end])
        if batch_v1:
            embeddings.extend(batch_v1)
        if batch_v2:
            embeddings_v2.extend(batch_v2)
    logger.info("[UPLOAD] 임베딩 완료 (%.1fs)", time.perf_counter() - t1)

    # 5. DB 저장
    uid = _uuid.UUID(user_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            deleted = await conn.fetchval(
                "SELECT COUNT(*) FROM documents WHERE metadata->>'source' = $1 AND user_id = $2",
                filename, uid,
            )
            if deleted:
                await conn.execute(
                    "DELETE FROM documents WHERE metadata->>'source' = $1 AND user_id = $2",
                    filename, uid,
                )
                logger.info("[UPLOAD] 기존 청크 %d개 삭제 (덮어쓰기)", deleted)
            await conn.executemany(
                "INSERT INTO documents (content, embedding, embedding_v2, metadata, user_id) "
                "VALUES ($1, $2, $3, $4, $5)",
                [
                    (
                        chunk,
                        embeddings[idx] if embeddings else None,
                        embeddings_v2[idx] if embeddings_v2 else None,
                        {**metadata_base, **structured_chunks[idx].metadata, "chunk_index": idx},
                        uid,
                    )
                    for idx, chunk in enumerate(chunks)
                ],
            )
            await conn.execute('''INSERT INTO user_document_files(user_id,filename,content,sha256)
                VALUES($1,$2,$3,$4) ON CONFLICT(user_id,filename) DO UPDATE
                SET content=EXCLUDED.content,sha256=EXCLUDED.sha256,uploaded_at=now()''',
                uid, filename, file_bytes, sha256(file_bytes).hexdigest())
            await conn.execute('DELETE FROM user_document_reviews WHERE user_id=$1 AND filename=$2', uid, filename)

    logger.info("[UPLOAD] 완료 — %d청크 저장 | 총 %.1fs", len(chunks), time.perf_counter() - t0)
    return {
        "status":        "ok",
        "filename":      filename,
        "law_name":      meta.get("law_name"),
        "category":      meta.get("category"),
        "chunks_stored": len(chunks),
        "format": extracted.format,
        "extraction_method": extracted.extraction_method,
        "ocr_pages": extracted.ocr_pages,
    }


async def list_documents(user_id: str) -> list[dict]:
    """사용자가 업로드한 파일 목록을 파일 단위로 반환한다 (청크 단위 아님)."""
    uid = _uuid.UUID(user_id)
    # SQL identifier is selected from a fixed allowlist, never user input.
    vector_column = "embedding_v2" if EMBEDDING_VERSION == "v2" else "embedding"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            WITH grouped AS (SELECT
                metadata->>'source'   AS filename,
                metadata->>'law_name' AS law_name,
                metadata->>'category' AS category,
                MAX(metadata->>'format') AS format,
                MAX(metadata->>'extraction_method') AS extraction_method,
                MAX((metadata->>'ocr_pages')::integer) AS ocr_pages,
                MAX((metadata->>'chunking_version')::integer) AS chunking_version,
                COUNT(*)              AS chunk_count,
                COUNT({vector_column}) AS embedded_count,
                MIN(created_at)       AS uploaded_at
            FROM documents
            WHERE user_id = $1 AND metadata->>'source' IS NOT NULL
            GROUP BY
                metadata->>'source',
                metadata->>'law_name',
                metadata->>'category'
            )
            SELECT grouped.*, EXISTS (SELECT 1 FROM user_document_files f
                WHERE f.user_id=$1 AND f.filename=grouped.filename) AS original_available
            FROM grouped ORDER BY uploaded_at DESC
            """,
            uid,
        )
    return [
        {
            "filename":    r["filename"],
            "law_name":    r["law_name"],
            "category":    r["category"],
            "format": r.get("format") or (r["filename"].rsplit('.', 1)[-1].lower() if r["filename"] and '.' in r["filename"] else None),
            "extraction_method": r.get("extraction_method") or "text",
            "ocr_pages": r.get("ocr_pages") or 0,
            "chunking_version": r.get("chunking_version"),
            "chunk_count": r["chunk_count"],
            "embedded_count": r["embedded_count"],
            "search_ready": r["chunk_count"] > 0 and r["embedded_count"] == r["chunk_count"],
            "uploaded_at": r["uploaded_at"].isoformat() if r["uploaded_at"] else None,
            "original_available": r.get("original_available", False),
        }
        for r in rows
    ]


async def delete_document(filename: str, user_id: str) -> dict:
    """사용자 소유 파일의 모든 청크를 삭제한다."""
    uid = _uuid.UUID(user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                "DELETE FROM documents WHERE metadata->>'source' = $1 AND user_id = $2 RETURNING id",
                filename, uid,
            )
            await conn.execute('DELETE FROM user_document_files WHERE user_id=$1 AND filename=$2', uid, filename)
    deleted_count = len(rows)
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    logger.info("[DELETE] '%s' 삭제 완료 — %d청크", filename, deleted_count)
    return {"status": "ok", "filename": filename, "deleted_chunks": deleted_count}
