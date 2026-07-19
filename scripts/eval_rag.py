"""
scripts/eval_rag.py — RAG 검색/답변 품질 평가 CLI

골든 평가셋(tests/eval/golden_qa.json)을 기준으로 실제 검색 파이프라인의
retrieval hit-rate·MRR·세목 분류 정확도를 측정하고, 결과를 tests/eval/results/에
타임스탬프 파일로 저장하여 이후 파라미터 변경 시 회귀 여부를 비교할 수 있게 한다.

사용법:
  # 1) 아직 정답(expected_article_no)이 없는 항목에 실제 DB 검색 후보를 채워넣기
  #    (candidates만 채워짐 — 정답은 사람이 검토 후 golden_qa.json에 직접 기입)
  python scripts/eval_rag.py --build

  # 2) 정답이 채워진 항목만 대상으로 검색 품질 평가 (빠름, LLM 답변 생성 없음)
  python scripts/eval_rag.py --eval

  # 3) 검색 평가 + 실제 답변 생성 후 인용 조문 정확도까지 확인 (느림, Ollama 호출)
  python scripts/eval_rag.py --eval --with-answer

  # 4) temperature 샘플링 편차 검증: 동일 평가를 N회 반복해 citation_accuracy 평균/편차와
  #    실행마다 결과가 바뀌는 비결정적 항목을 확인 (프롬프트/코드 변경의 실제 개선 여부는
  #    단일 실행 비교로 판단할 수 없음이 실측으로 확인됨 — README 트러블슈팅 참고)
  python scripts/eval_rag.py --eval --with-answer --repeat 3
"""
import argparse
import asyncio
import json
import re
import sys
import time
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import close_pool, get_pool
from app.services.chat_service import _classify_and_generate_queries, process_chat
from app.services.llm_client import close_llm_client
from app.services.search.hybrid_search_service import hybrid_search
from app.utils.embeddings import close_http_client
from config import TOP_K

_GOLDEN_PATH  = Path(__file__).resolve().parent.parent / "tests" / "eval" / "golden_qa.json"
_RESULTS_DIR  = Path(__file__).resolve().parent.parent / "tests" / "eval" / "results"
_EVAL_USER_ID = "00000000-0000-0000-0000-000000000001"

# 답변 인용 추출은 운영 코드(citation_guard)와 동일한 파서를 사용한다 —
# 평가기와 운영기가 다른 정규식을 쓰면 측정이 실제 동작을 반영하지 못한다.
# (과거: 공백 포함 법령명 '상속세 및 증여세법', 공백 섞인 조문번호 '제 50 조'를
#  평가기가 못 잡아 citation_accuracy가 18.4%로 왜곡 측정된 사례)
from app.services.citation_guard import extract_citations as _extract_guard_citations


def _load_golden() -> dict:
    return json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))


def _save_golden(data: dict) -> None:
    _GOLDEN_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _content_header(content: str) -> str:
    """HybridSearchResult.content 첫 줄(조문번호+제목 또는 청크 스니펫)."""
    return content.split("\n", 1)[0][:80]


async def build_candidates() -> None:
    """모든 항목에 대해 실제 검색을 실행하고 후보를 candidates에 채운다 (정답은 채우지 않음)."""
    data = _load_golden()
    items = data["items"]
    print(f"후보 채우기 시작 — {len(items)}건\n")

    for item in items:
        law_filter = item["expected_law_name"] or "ALL"
        results = await hybrid_search(
            [item["query"]], law_filter=law_filter,
            user_id=_EVAL_USER_ID, original_query=item["query"],
        )
        item["candidates"] = [
            {
                "source_type": r.source_type,
                "law_name": r.law_name,
                "category": r.category,
                "header": _content_header(r.content),
                "similarity_score": r.similarity_score,
            }
            for r in results
        ]
        mark = "확정" if item.get("expected_article_no") else "미확정"
        print(f"  [{item['id']}] ({mark}) 후보 {len(results)}건 — {item['query'][:30]}")

    _save_golden(data)
    print(f"\n완료 — {_GOLDEN_PATH} 에 candidates 저장됨.")
    print("expected_article_no가 null인 항목은 candidates를 검토하여 직접 정답을 채워주세요.")


def _norm(s: str) -> str:
    """법령명 공백 표기 차이를 무시하고 비교하기 위한 정규화(방어적 안전장치)."""
    return re.sub(r"\s+", "", s)


def _find_hit_rank(results, expected_law_name: str, expected_article_no: str) -> int | None:
    for rank, r in enumerate(results, start=1):
        if _norm(r.law_name) == _norm(expected_law_name) and expected_article_no in _content_header(r.content):
            return rank
    return None


def _extract_citations(answer: str) -> list[tuple[str, str]]:
    """운영 인용 파서(citation_guard.extract_citations)를 재사용 — (법령명, 조문번호) 반환."""
    return [(law_name, article_no) for _label, law_name, article_no in _extract_guard_citations(answer)]


async def run_eval(with_answer: bool) -> tuple[dict, list[dict]]:
    data = _load_golden()
    graded = [it for it in data["items"] if it.get("expected_article_no")]
    skipped = len(data["items"]) - len(graded)
    if not graded:
        print("expected_article_no가 채워진 항목이 없습니다. 먼저 --build 후 정답을 채워주세요.")
        return {}, []

    print(f"평가 대상 {len(graded)}건 (미확정 {skipped}건 제외) | TOP_K={TOP_K} | with_answer={with_answer}\n")

    rows = []
    for item in graded:
        t0 = time.perf_counter()
        law_filter, queries = await _classify_and_generate_queries(item["query"])
        results = await hybrid_search(
            queries, law_filter=law_filter,
            user_id=_EVAL_USER_ID, original_query=item["query"],
        )
        elapsed = time.perf_counter() - t0

        hit_rank = _find_hit_rank(results, item["expected_law_name"], item["expected_article_no"])
        classification_exact = law_filter == item["expected_law_name"]
        classification_fallback_all = law_filter == "ALL"

        row = {
            "id": item["id"],
            "query": item["query"],
            "expected": f"{item['expected_law_name']} {item['expected_article_no']}",
            "predicted_law_filter": law_filter,
            "classification_exact": classification_exact,
            "classification_fallback_all": classification_fallback_all,
            "hit_rank": hit_rank,
            "elapsed_sec": round(elapsed, 2),
        }

        if with_answer:
            conv_id = str(_uuid.uuid4())
            # process_chat은 (답변, 계산기 메타데이터) 튜플을 반환한다
            answer, _calc_meta = await process_chat(item["query"], conv_id, _EVAL_USER_ID)
            citations = _extract_citations(answer)
            # 법령명 공백 표기 차이('상속세및증여세법' vs '상속세 및 증여세법')는 무시하고 비교
            row["citation_hit"] = any(
                _norm(law) == _norm(item["expected_law_name"]) and art == item["expected_article_no"]
                for law, art in citations
            )
            row["citations_found"] = [f"{law} {art}" for law, art in citations]
            row["answer_chars"] = len(answer)

        rows.append(row)
        status = f"HIT@{hit_rank}" if hit_rank else "MISS"
        cite = ""
        if with_answer:
            cite = " | 인용:" + ("O" if row["citation_hit"] else "X")
        print(f"  [{item['id']}] {status:8s} | 분류={law_filter:12s} ({'정확' if classification_exact else '불일치'}){cite}  ({elapsed:.1f}s)")

    total = len(rows)
    hits = [r for r in rows if r["hit_rank"]]
    hit_rate = len(hits) / total
    mrr = sum(1 / r["hit_rank"] for r in hits) / total
    classification_accuracy = sum(1 for r in rows if r["classification_exact"]) / total

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "skipped_ungraded": skipped,
        "top_k": TOP_K,
        "hit_rate_at_k": round(hit_rate, 4),
        "mrr": round(mrr, 4),
        "classification_accuracy": round(classification_accuracy, 4),
        "with_answer": with_answer,
    }
    if with_answer:
        citation_hits = sum(1 for r in rows if r.get("citation_hit"))
        summary["citation_accuracy"] = round(citation_hits / total, 4)

    print(f"\n{'='*60}")
    print(f" 검색 hit_rate@{TOP_K}: {hit_rate:.1%}  |  MRR: {mrr:.3f}  |  세목 분류 정확도: {classification_accuracy:.1%}")
    if with_answer:
        print(f" 인용 정확도(citation_accuracy): {summary['citation_accuracy']:.1%}")
    print(f"{'='*60}")

    misses = [r for r in rows if not r["hit_rank"]]
    if misses:
        print(f"\nMISS 항목 ({len(misses)}건):")
        for r in misses:
            print(f"  - [{r['id']}] {r['query'][:40]} (기대: {r['expected']})")

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _RESULTS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n결과 저장: {out_path}")

    _print_regression_diff(summary)
    return summary, rows


async def run_eval_repeated(with_answer: bool, repeat: int) -> None:
    """동일 평가를 N회 반복 실행해 citation_accuracy 편차와 항목별 결과 불안정성을 확인한다.

    temperature=0.3 샘플링 특성상 답변 인용 여부가 실행마다 달라질 수 있어(실측: 동일 코드로
    재평가해도 81.6%↔73.7%로 흔들림), 단일 실행 결과만으로 프롬프트/코드 변경의 개선 여부를
    판단하면 잘못된 결론에 이를 수 있다. --repeat N으로 여러 번 돌려 평균과 함께,
    실행마다 결과가 바뀌는 항목(비결정적 항목)을 식별한다.
    """
    print(f"=== {repeat}회 반복 평가 시작 (with_answer={with_answer}) ===\n")
    citation_accuracies = []
    hit_history: dict[str, list[bool]] = {}

    for run_no in range(1, repeat + 1):
        print(f"\n--- 실행 {run_no}/{repeat} ---")
        summary, rows = await run_eval(with_answer)
        if not rows:
            return
        if with_answer:
            citation_accuracies.append(summary["citation_accuracy"])
            for r in rows:
                hit_history.setdefault(r["id"], []).append(r["citation_hit"])

    if not with_answer:
        return

    n = len(citation_accuracies)
    mean = sum(citation_accuracies) / n
    print(f"\n{'='*60}")
    print(f" citation_accuracy {repeat}회 반복 결과: {[f'{v:.1%}' for v in citation_accuracies]}")
    print(f" 평균: {mean:.1%}  |  최소: {min(citation_accuracies):.1%}  |  최대: {max(citation_accuracies):.1%}")
    print(f"{'='*60}")

    unstable = {k: v for k, v in hit_history.items() if len(set(v)) > 1}
    if unstable:
        print(f"\n실행마다 인용 히트 여부가 바뀐 비결정적 항목 ({len(unstable)}건):")
        for item_id, history in unstable.items():
            print(f"  - [{item_id}]: {history}")
    else:
        print("\n모든 항목이 반복 실행 내내 동일한 결과 — 이번 변경은 안정적으로 보임.")


def _print_regression_diff(summary: dict) -> None:
    """직전 실행 결과와 비교하여 지표 변화를 출력한다."""
    prior_runs = sorted(_RESULTS_DIR.glob("*.json"))[:-1]
    if not prior_runs:
        return
    prev = json.loads(prior_runs[-1].read_text(encoding="utf-8"))["summary"]
    print(f"\n직전 실행({prior_runs[-1].name}) 대비:")
    for key in ("hit_rate_at_k", "mrr", "classification_accuracy"):
        if key in prev:
            delta = summary[key] - prev[key]
            sign = "+" if delta >= 0 else ""
            print(f"  {key}: {prev[key]:.4f} → {summary[key]:.4f} ({sign}{delta:.4f})")


async def main(args: argparse.Namespace) -> None:
    print("DB 연결 중...")
    await get_pool()
    print("DB 연결 완료\n")
    try:
        if args.build:
            await build_candidates()
        elif args.eval:
            if args.repeat > 1:
                await run_eval_repeated(with_answer=args.with_answer, repeat=args.repeat)
            else:
                await run_eval(with_answer=args.with_answer)
        else:
            print("--build 또는 --eval 중 하나를 지정하세요.")
    finally:
        await close_pool()
        await close_http_client()
        await close_llm_client()
        print("\nDB 연결 종료")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG 검색/답변 품질 평가 스크립트")
    parser.add_argument("--build",       action="store_true", help="골든셋 각 질문의 실제 검색 후보를 candidates에 채움")
    parser.add_argument("--eval",        action="store_true", help="expected_article_no가 채워진 항목으로 hit-rate/MRR/분류정확도 평가")
    parser.add_argument("--with-answer", action="store_true", help="--eval 과 함께: 실제 답변 생성 후 인용 조문 정확도까지 확인 (느림)")
    parser.add_argument("--repeat", type=int, default=1, help="--eval을 N회 반복해 citation_accuracy 편차와 비결정적 항목을 확인 (temperature 샘플링 검증용)")
    args = parser.parse_args()
    asyncio.run(main(args))
