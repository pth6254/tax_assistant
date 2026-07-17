"""
services/law/interpretation_service.py — 법령해석례(유권해석) 수집·저장·임베딩

국가법령정보 Open API(target=expc)로 세무 관련 유권해석(기획재정부·국세청 등의
법령해석)을 검색해 law_articles 테이블에 law_type='법령해석례'로 저장한다.

법령 조문과 동일한 테이블·검색 경로(hybrid_search_service)를 그대로 재사용하므로
검색 파이프라인 변경 없이 자료 종류만 하나 늘어난다 — 조문 저장/임베딩에 쓰는
ingestion_service의 내부 유틸(_insert_article_returning_id 등)을 그대로 재사용한다.

사용 예:
  from app.services.law.interpretation_service import ingest_interpretations
  result = await ingest_interpretations("소득세", embed=True, max_results=50)
"""
import asyncio
import logging
import re

from app.database import get_pool
from app.schemas.law import LawArticle
from app.services.law.api_service import get_expc_detail, search_expc
from app.services.law.ingestion_service import (
    _embed_and_update,
    _infer_tax_type,
    _insert_article_returning_id,
    _make_hash,
)

logger = logging.getLogger(__name__)

# 법제처 법령해석례 공개 뷰어 (조문 원문의 lsInfoP.do와 동일한 성격의 공개 페이지)
_SOURCE_URL_TEMPLATE = "https://www.law.go.kr/expcInfoP.do?expcSeq={case_id}"

# 안건명에 포함된 「법령명」에서 관련 법령을 추출 (예: "「소득세법」 제20조..." → "소득세법")
_BRACKETED_LAW_RE = re.compile(r"「([^」]+)」")


def _extract_law_name(title: str) -> str:
    """안건명에서 첫 번째 「법령명」을 추출한다. 없으면 '법령해석례' 반환."""
    match = _BRACKETED_LAW_RE.search(title)
    return match.group(1) if match else "법령해석례"


def _build_article_text(detail: dict) -> str:
    """질의요지/회답/이유를 하나의 조문 본문 형태로 합친다."""
    sections = [
        ("질의요지", detail.get("question", "")),
        ("회답",     detail.get("answer", "")),
        ("이유",     detail.get("reasoning", "")),
    ]
    return "\n\n".join(f"[{label}]\n{text}" for label, text in sections if text)


async def _search_all_pages(
    query: str,
    max_results: int,
    request_delay: float,
) -> list[dict]:
    """법령해석례 목록을 페이지네이션하여 최대 max_results건 수집한다."""
    summaries: list[dict] = []
    page = 1
    display = min(max_results, 100)

    while len(summaries) < max_results:
        batch = await search_expc(query, display=display, page=page)
        if not batch:
            break
        summaries.extend(batch)
        if len(batch) < display:
            break
        page += 1
        if request_delay > 0:
            await asyncio.sleep(request_delay)

    return summaries[:max_results]


async def ingest_interpretations(
    query: str,
    *,
    embed: bool = False,
    max_results: int = 100,
    request_delay: float = 0.2,
) -> dict:
    """
    세무 관련 유권해석을 키워드로 검색하여 law_articles에 저장한다.

    Args:
        query:         검색 키워드 (예: "소득세", "부가가치세")
        embed:         True이면 신규 저장 건에 대해 임베딩 생성
        max_results:   최대 수집 건수 (API 부하 방지용 상한)
        request_delay: 본문 조회 API 호출 간 대기시간(초) — 과도한 요청 방지

    Returns:
        {"query", "found", "inserted_count", "skipped_count",
         "failed_count", "embedded_count", "embed_failed_count"}
    """
    summaries = await _search_all_pages(query, max_results, request_delay)
    logger.info("[expc] '%s' 검색 결과 %d건", query, len(summaries))

    inserted_count = 0
    skipped_count  = 0
    failed_count   = 0
    # tax_type별로 묶어야 임베딩 텍스트에 올바른 세목이 들어간다
    embed_groups: dict[str, list[tuple[LawArticle, int]]] = {}

    pool = await get_pool()
    async with pool.acquire() as conn:
        for summary in summaries:
            case_id = summary.get("case_id")
            if not case_id:
                continue

            try:
                detail = await get_expc_detail(case_id)
            except Exception as e:
                logger.warning("[expc] 본문 조회 실패 case_id=%s: %s", case_id, e)
                failed_count += 1
                continue
            finally:
                if request_delay > 0:
                    await asyncio.sleep(request_delay)

            article_text = _build_article_text(detail)
            if not article_text:
                skipped_count += 1
                continue

            law_name = _extract_law_name(detail.get("title", ""))
            tax_type = _infer_tax_type(law_name)

            article = LawArticle(
                law_name=law_name,
                law_type="법령해석례",
                article_no=detail.get("case_no") or case_id,
                article_title=detail.get("title", ""),
                article_text=article_text,
                effective_date=detail.get("decision_date", ""),
                amendment_date="",
            )
            source_url   = _SOURCE_URL_TEMPLATE.format(case_id=case_id)
            content_hash = _make_hash(article.article_text)

            try:
                new_id = await _insert_article_returning_id(conn, article, tax_type, source_url, content_hash)
            except Exception as e:
                logger.warning("[expc] 저장 실패 case_id=%s: %s", case_id, e)
                failed_count += 1
                continue

            if new_id is not None:
                inserted_count += 1
                embed_groups.setdefault(tax_type, []).append((article, new_id))
            else:
                skipped_count += 1

    embedded_count      = 0
    embed_failed_count  = 0
    if embed:
        for tax_type, items in embed_groups.items():
            e, f = await _embed_and_update(items, tax_type)
            embedded_count      += e
            embed_failed_count  += f

    return {
        "query":               query,
        "found":               len(summaries),
        "inserted_count":      inserted_count,
        "skipped_count":       skipped_count,
        "failed_count":        failed_count,
        "embedded_count":      embedded_count,
        "embed_failed_count":  embed_failed_count,
    }
