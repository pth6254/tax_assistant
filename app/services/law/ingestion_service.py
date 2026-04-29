"""
services/law_ingestion_service.py — 법령 조문 수집·저장·임베딩 파이프라인

Phase 4: 조문 메타데이터 저장 (embedding=NULL)
Phase 5: 신규 조문 임베딩 생성 및 저장

주요 함수:
  ingest_law(law_name, tax_type, embed=False)   단일 법령 수집
  ingest_all_laws(embed=False)                  전체 세목 법령 일괄 수집
"""
import hashlib

from app.database import get_pool
from app.services.law.api_service import LawSummary, get_law_detail, search_law
from app.services.law.parser_service import LawArticle, parse_articles
from config import EMBED_DIM, EMBED_MODEL

_SOURCE_URL_TEMPLATE = "https://www.law.go.kr/lsInfoP.do?lsiSeq={mst}"
_EMBED_BATCH_SIZE = 100

# 수집 대상 법령 목록 — chat_service._LAW_KW 세목 키와 동일하게 유지
# 순서: 법령 위계 (상위법 → 하위법) 기준
LAW_TARGETS: list[dict] = [
    {"law_name": "국세기본법",       "tax_type": "국세기본법"},
    {"law_name": "소득세법",         "tax_type": "소득세법"},
    {"law_name": "법인세법",         "tax_type": "법인세법"},
    {"law_name": "부가가치세법",     "tax_type": "부가가치세법"},
    {"law_name": "상속세및증여세법", "tax_type": "상속세및증여세법"},
    {"law_name": "조세특례제한법",   "tax_type": "조세특례제한법"},
    {"law_name": "지방세법",         "tax_type": "지방세법"},
]


# ── 내부 유틸 ────────────────────────────────────────────────────

def _make_hash(text: str) -> str:
    """article_text SHA-256 해시. content_hash 컬럼에 저장."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_embed_text(article: LawArticle, tax_type: str) -> str:
    """
    임베딩용 컨텍스트 텍스트 생성.
    법령 메타데이터를 앞에 붙여 검색 품질을 높인다.
    """
    return (
        f"법령명: {article.law_name}\n"
        f"문서유형: {article.law_type}\n"
        f"세목: {tax_type}\n"
        f"조문: {article.article_no}\n"
        f"제목: {article.article_title}\n"
        f"내용:\n{article.article_text}"
    )


async def _find_exact_law(law_name: str) -> LawSummary | None:
    """법령명 완전일치 검색. 결과 없으면 None."""
    laws = await search_law(law_name, display=20, exact=True)
    return laws[0] if laws else None


async def _insert_article_returning_id(
    conn,
    article: LawArticle,
    tax_type: str,
    source_url: str,
    content_hash: str,
) -> int | None:
    """
    조문 1건을 INSERT하고 신규 삽입된 행의 id를 반환한다.

    Returns:
        int   신규 삽입 성공 — 삽입된 행의 id
        None  중복 스킵 (ON CONFLICT DO NOTHING)

    Raises:
        Exception: INSERT 실패 (호출자가 처리)
    """
    row = await conn.fetchrow(
        """
        INSERT INTO law_articles (
            law_name, law_type, tax_type,
            article_no, article_title, article_text,
            effective_date, amendment_date,
            source_url, content_hash,
            embedding, is_current
        ) VALUES (
            $1,  $2,  $3,
            $4,  $5,  $6,
            $7,  $8,
            $9,  $10,
            NULL, TRUE
        )
        ON CONFLICT (law_name, article_no, content_hash) DO NOTHING
        RETURNING id
        """,
        article.law_name,
        article.law_type,
        tax_type,
        article.article_no,
        article.article_title,
        article.article_text,
        article.effective_date,
        article.amendment_date,
        source_url,
        content_hash,
    )
    return row["id"] if row else None


async def _embed_and_update(
    new_items: list[tuple[LawArticle, int]],
    tax_type: str,
) -> tuple[int, int]:
    """
    신규 삽입된 조문에 대해 임베딩을 생성하고 law_articles.embedding을 업데이트한다.

    Args:
        new_items: [(LawArticle, db_id), ...] — INSERT RETURNING id로 수집된 신규 조문
        tax_type:  임베딩 텍스트 구성에 사용

    Returns:
        (embedded_count, embed_failed_count)
    """
    from app.utils.embeddings import embed_texts  # 기존 PDF 임베딩 함수 재사용

    embedded_count    = 0
    embed_failed_count = 0
    total = len(new_items)

    pool = await get_pool()

    for batch_start in range(0, total, _EMBED_BATCH_SIZE):
        batch = new_items[batch_start : batch_start + _EMBED_BATCH_SIZE]
        batch_end = batch_start + len(batch)
        texts  = [_build_embed_text(art, tax_type) for art, _ in batch]
        db_ids = [db_id for _, db_id in batch]

        print(f"  [embed] {batch_start + 1}~{batch_end} / {total} 임베딩 중...")

        try:
            embeddings = await embed_texts(texts)

            # 차원 불일치 검증
            for emb in embeddings:
                if len(emb) != EMBED_DIM:
                    raise ValueError(
                        f"임베딩 차원 불일치: 예상 {EMBED_DIM}차원, 실제 {len(emb)}차원. "
                        f"현재 EMBED_MODEL='{EMBED_MODEL}'. "
                        f".env의 EMBED_MODEL과 init_db.sql의 VECTOR({EMBED_DIM})이 "
                        f"일치하는지 확인하세요."
                    )

            async with pool.acquire() as conn:
                await conn.executemany(
                    "UPDATE law_articles SET embedding = $1 WHERE id = $2",
                    list(zip(embeddings, db_ids)),
                )

            embedded_count += len(batch)
            print(f"  [embed] {batch_end} / {total} 완료")

        except Exception as e:
            embed_failed_count += len(batch)
            print(f"  [embed] 배치 실패 ({batch_start + 1}~{batch_end}): {e}")

    return embedded_count, embed_failed_count


# ── 공개 함수 ────────────────────────────────────────────────────

async def ingest_law(
    law_name: str,
    tax_type: str,
    law_type: str = "",
    *,
    embed: bool = False,
) -> dict:
    """
    법령명으로 API를 호출해 조문을 파싱하고 law_articles 테이블에 저장한다.

    Args:
        law_name: 검색할 법령명 (예: "소득세법")
        tax_type: 세목 분류 — chat_service._LAW_KW 키와 맞출 것
        law_type: 법령종류 힌트 (API 결과로 덮어씌워짐)
        embed:    True이면 신규 삽입된 조문에 대해 임베딩 생성

    Returns:
        {
            "law_name":          str,
            "mst":               str,
            "total_articles":    int,
            "inserted_count":    int,
            "skipped_count":     int,
            "failed_count":      int,
            "embedded_count":    int,   # embed=False이면 항상 0
            "embed_failed_count": int,  # embed=False이면 항상 0
        }

    Raises:
        ValueError: API 키 미설정 / 법령 검색 결과 없음
        httpx.TimeoutException / HTTPStatusError: API 통신 오류
    """
    # ── 1. 법령 검색 ────────────────────────────────────────────
    law_summary = await _find_exact_law(law_name)
    if law_summary is None:
        raise ValueError(
            f"'{law_name}' 완전일치 검색 결과가 없습니다. "
            "법령명을 확인하거나 exact=False로 재시도하세요."
        )

    mst               = law_summary.mst
    source_url        = _SOURCE_URL_TEMPLATE.format(mst=mst)
    resolved_law_type = law_summary.law_type or law_type

    # ── 2. 법령 원문 XML 조회 ────────────────────────────────────
    print(f"  [api] '{law_name}' XML 조회 중 (MST={mst})...")
    detail  = await get_law_detail(mst)
    raw_xml = detail["raw_xml"]

    # ── 3. 조문 파싱 ─────────────────────────────────────────────
    articles = parse_articles(
        raw_xml,
        law_name_hint=law_name,
        law_type_hint=resolved_law_type,
    )
    print(f"  [parse] {len(articles)}개 조문 파싱 완료")

    if not articles:
        return {
            "law_name":           law_name,
            "mst":                mst,
            "total_articles":     0,
            "inserted_count":     0,
            "skipped_count":      0,
            "failed_count":       0,
            "embedded_count":     0,
            "embed_failed_count": 0,
        }

    # ── 4. DB 저장 ───────────────────────────────────────────────
    inserted_count = 0
    skipped_count  = 0
    failed_count   = 0
    new_items: list[tuple[LawArticle, int]] = []  # 신규 삽입된 (article, db_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        for article in articles:
            content_hash = _make_hash(article.article_text)
            try:
                new_id = await _insert_article_returning_id(
                    conn, article, tax_type, source_url, content_hash
                )
                if new_id is not None:
                    inserted_count += 1
                    new_items.append((article, new_id))
                else:
                    skipped_count += 1
            except Exception as e:
                failed_count += 1
                print(f"  [db] 저장 실패: {article.article_no} — {e}")

    print(
        f"  [db] 저장 완료 — 신규 {inserted_count}건 | "
        f"스킵 {skipped_count}건 | 실패 {failed_count}건"
    )

    # ── 5. 임베딩 생성 (신규 삽입 조문만) ─────────────────────────
    embedded_count    = 0
    embed_failed_count = 0

    if embed and new_items:
        print(f"  [embed] {len(new_items)}건 임베딩 시작...")
        embedded_count, embed_failed_count = await _embed_and_update(new_items, tax_type)
        print(
            f"  [embed] 완료 — 성공 {embedded_count}건 | 실패 {embed_failed_count}건"
        )
    elif embed and not new_items:
        print(f"  [embed] 신규 조문 없음, 임베딩 생략")

    return {
        "law_name":           law_name,
        "mst":                mst,
        "total_articles":     len(articles),
        "inserted_count":     inserted_count,
        "skipped_count":      skipped_count,
        "failed_count":       failed_count,
        "embedded_count":     embedded_count,
        "embed_failed_count": embed_failed_count,
    }


async def ingest_all_laws(
    targets: list[dict] | None = None,
    *,
    embed: bool = False,
) -> list[dict]:
    """
    여러 법령을 순차적으로 수집하여 law_articles에 저장한다.

    Args:
        targets: 수집 대상 목록. None이면 LAW_TARGETS 전체 사용.
                 형식: [{"law_name": str, "tax_type": str}, ...]
        embed:   True이면 각 법령 수집 후 임베딩 생성

    Returns:
        법령별 ingest_law() 결과 리스트.
        오류 발생 법령은 {"law_name": ..., "error": ...} 형식.
    """
    targets = targets if targets is not None else LAW_TARGETS
    results: list[dict] = []

    for i, target in enumerate(targets, 1):
        law_name = target["law_name"]
        tax_type = target["tax_type"]
        print(f"\n[{i}/{len(targets)}] '{law_name}' 수집 시작...")

        try:
            result = await ingest_law(
                law_name=law_name,
                tax_type=tax_type,
                embed=embed,
            )
            embed_info = (
                f" | 임베딩 {result['embedded_count']}건"
                if embed else ""
            )
            print(
                f"  완료 — 파싱 {result['total_articles']}건 | "
                f"저장 {result['inserted_count']}건 | "
                f"스킵 {result['skipped_count']}건 | "
                f"실패 {result['failed_count']}건"
                f"{embed_info}"
            )
            results.append(result)

        except Exception as e:
            print(f"  오류 — {type(e).__name__}: {e}")
            results.append({"law_name": law_name, "error": str(e)})

    # 최종 요약
    success        = [r for r in results if "error" not in r]
    total_inserted = sum(r["inserted_count"]    for r in success)
    total_skipped  = sum(r["skipped_count"]     for r in success)
    total_failed   = sum(r["failed_count"]      for r in success)
    total_embedded = sum(r["embedded_count"]    for r in success)
    error_laws     = [r["law_name"] for r in results if "error" in r]

    print(f"\n{'='*40}")
    print(f" 전체 수집 완료")
    print(f"  법령 수:   {len(results)}개 ({len(success)}개 성공, {len(error_laws)}개 오류)")
    print(f"  신규 저장: {total_inserted}건")
    print(f"  중복 스킵: {total_skipped}건")
    print(f"  저장 실패: {total_failed}건")
    if embed:
        print(f"  임베딩:    {total_embedded}건")
    if error_laws:
        print(f"  오류 법령: {', '.join(error_laws)}")
    print(f"{'='*40}")

    return results
