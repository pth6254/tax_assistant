"""
scripts/ingest_laws.py — 법령 수집 CLI

사용법:
  # 세법 전체 자동 탐색 + 저장 (임베딩 없이)
  python scripts/ingest_laws.py

  # 임베딩까지 함께 생성 (Ollama 실행 필요)
  python scripts/ingest_laws.py --embed

  # 이미 저장된 조문 중 embedding=NULL 인 것만 임베딩
  python scripts/ingest_laws.py --embed-only
  python scripts/ingest_laws.py --embed-only --tax-type 소득세법

  # 기존 7개 주요 법령만 수집
  python scripts/ingest_laws.py --targets-only

  # 특정 법령 1개만 수집
  python scripts/ingest_laws.py --law 소득세법
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import close_pool, get_pool
from app.utils.embeddings import close_http_client, embed_texts
from app.services.law.ingestion_service import (
    LAW_TARGETS,
    ingest_all_laws,
    ingest_all_tax_laws,
    ingest_law,
    _infer_tax_type,
)
from config import EMBED_DIM, EMBED_MODEL


async def embed_only(tax_type: str, batch_size: int) -> None:
    """embedding = NULL 인 조문에만 임베딩을 생성한다."""
    pool = await get_pool()

    where_extra = "AND tax_type = $3" if tax_type else ""
    count_params = [batch_size, 0, tax_type] if tax_type else [batch_size, 0]

    if tax_type:
        total = await pool.fetchval(
            "SELECT COUNT(*) FROM law_articles WHERE embedding IS NULL AND is_current = TRUE AND tax_type = $1",
            tax_type,
        )
    else:
        total = await pool.fetchval(
            "SELECT COUNT(*) FROM law_articles WHERE embedding IS NULL AND is_current = TRUE"
        )

    if total == 0:
        print("임베딩이 필요한 조문이 없습니다.")
        return

    print(f"임베딩 대상: {total}건 | 모델: {EMBED_MODEL} ({EMBED_DIM}차원) | 배치: {batch_size}\n")

    processed = 0
    failed = 0
    offset = 0

    while True:
        if tax_type:
            rows = await pool.fetch(
                """
                SELECT id, law_name, law_type, tax_type,
                       article_no, article_title, article_text
                FROM law_articles
                WHERE embedding IS NULL AND is_current = TRUE AND tax_type = $1
                ORDER BY id LIMIT $2 OFFSET $3
                """,
                tax_type, batch_size, offset,
            )
        else:
            rows = await pool.fetch(
                """
                SELECT id, law_name, law_type, tax_type,
                       article_no, article_title, article_text
                FROM law_articles
                WHERE embedding IS NULL AND is_current = TRUE
                ORDER BY id LIMIT $1 OFFSET $2
                """,
                batch_size, offset,
            )

        if not rows:
            break

        texts = [
            f"법령명: {r['law_name']}\n문서유형: {r['law_type']}\n세목: {r['tax_type']}\n"
            f"조문: {r['article_no']}\n제목: {r['article_title']}\n내용:\n{r['article_text']}"
            for r in rows
        ]
        ids = [r["id"] for r in rows]

        print(f"  [{offset + 1}~{offset + len(rows)} / {total}] 임베딩 생성 중...")

        try:
            embeddings = await embed_texts(texts)

            for emb in embeddings:
                if len(emb) != EMBED_DIM:
                    raise ValueError(
                        f"차원 불일치: 예상 {EMBED_DIM}, 실제 {len(emb)} — "
                        f"EMBED_MODEL={EMBED_MODEL} 과 DB VECTOR({EMBED_DIM}) 확인"
                    )

            await pool.executemany(
                "UPDATE law_articles SET embedding = $1 WHERE id = $2",
                list(zip(embeddings, ids)),
            )
            processed += len(rows)
            print(f"  완료 ({processed}/{total})")

        except Exception as e:
            failed += len(rows)
            print(f"  배치 실패: {e}")

        offset += batch_size

    print(f"\n{'='*40}")
    print(f" 임베딩 완료 — 성공 {processed}건 | 실패 {failed}건")
    print(f"{'='*40}")


async def main(args: argparse.Namespace) -> None:
    print("DB 연결 중...")
    await get_pool()
    print("DB 연결 완료\n")

    try:
        if args.embed_only:
            await embed_only(tax_type=args.tax_type, batch_size=args.batch_size)

        elif args.law:
            law_name = args.law
            tax_type = _infer_tax_type(law_name)
            print(f"'{law_name}' (세목: {tax_type}) 수집 시작...")
            result = await ingest_law(law_name=law_name, tax_type=tax_type, embed=args.embed)
            print(f"\n결과: {result}")

        elif args.targets_only:
            print(f"주요 세법 {len(LAW_TARGETS)}개 수집 시작...")
            results = await ingest_all_laws(targets=LAW_TARGETS, embed=args.embed)
            _print_summary(results)

        else:
            results = await ingest_all_tax_laws(embed=args.embed)
            _print_summary(results)

    finally:
        await close_pool()
        await close_http_client()
        print("\nDB 연결 종료")


def _print_summary(results: list[dict]) -> None:
    success = [r for r in results if "error" not in r]
    errors  = [r for r in results if "error" in r]
    print(f"\n{'='*50}")
    print(f"총 {len(results)}개 법령 처리")
    print(f"  성공: {len(success)}개")
    print(f"  오류: {len(errors)}개")
    if errors:
        for r in errors:
            print(f"  ✗ {r['law_name']}: {r['error']}")
    print(f"{'='*50}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="법령 수집 / 임베딩 스크립트")
    parser.add_argument("--embed",       action="store_true", help="수집 시 임베딩 생성")
    parser.add_argument("--embed-only",  action="store_true", help="저장된 조문 중 embedding=NULL 만 임베딩")
    parser.add_argument("--tax-type",    type=str, default="", help="--embed-only 시 특정 세목만 (예: 소득세법)")
    parser.add_argument("--batch-size",  type=int, default=50, help="임베딩 배치 크기 (기본 50)")
    parser.add_argument("--targets-only",action="store_true", help="LAW_TARGETS 7개 법령만 수집")
    parser.add_argument("--law",         type=str, default="", help="단일 법령 수집 (예: --law 소득세법)")
    args = parser.parse_args()
    asyncio.run(main(args))
