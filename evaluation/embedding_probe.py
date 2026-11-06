"""Read-only statute retrieval probe over evaluation/datasets/embedding_retrieval.json.

Two modes, scored the same way (a case is hit when a required or acceptable article is in the top k):
- vector: the embedding alone. The query is embedded with the service's embedding client and query
  instruction, and matched against the stored current-statute article and clause vectors (a clause
  hit counts as its article). Legal interpretations are left out of the candidates, since an
  interpretation case would otherwise find its own text. This is the number to compare embedding
  models with.
- hybrid: the service's hybrid_search (BM25, vectors, direct article lookup; Graph off), i.e. what
  the answer pipeline actually gets.

No model calls besides the query embedding, no writes. Run inside the project, e.g.
    python evaluation/embedding_probe.py --mode vector --output evaluation/runs/embedding-probe/vector
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402

DATASET = Path(__file__).resolve().parent / "datasets" / "embedding_retrieval.json"
KS = (1, 5, 10, 20)
DEPTH = 20
CANDIDATES = 60
PROBE_USER = "00000000-0000-0000-0000-000000000000"

_VECTOR_SQL = """
WITH q AS (SELECT $1::vector::halfvec(2560) AS v)
SELECT law_name, article_no, max(score) AS score FROM (
    (SELECT a.law_name, a.article_no, 1 - (a.{col}::halfvec(2560) <=> q.v) AS score
     FROM law_articles a, q
     WHERE a.is_current AND a.law_type <> '법령해석례' AND a.{col} IS NOT NULL
     ORDER BY a.{col}::halfvec(2560) <=> q.v LIMIT $2)
    UNION ALL
    (SELECT a.law_name, a.article_no, 1 - (c.{col}::halfvec(2560) <=> q.v) AS score
     FROM law_article_clauses c JOIN law_articles a ON a.id = c.article_id, q
     WHERE a.is_current AND a.law_type <> '법령해석례' AND c.{col} IS NOT NULL
     ORDER BY c.{col}::halfvec(2560) <=> q.v LIMIT $2)
) hits GROUP BY law_name, article_no ORDER BY score DESC LIMIT $3
"""


def targets(case):
    return {(a["law"], a["article"]) for a in case["required"] + case["acceptable"]}


def first_hit(ranked, wanted):
    for rank, key in enumerate(ranked, 1):
        if key in wanted:
            return rank
    return None


async def vector_ranking(pool, query):
    from app.services.embedding_service import embed_texts
    from app.services.search.hybrid_search_service import _embedding_queries
    vector = (await embed_texts(_embedding_queries([query])))[0]
    column = "embedding_v2" if config.EMBEDDING_VERSION == "v2" else "embedding"
    async with pool.acquire() as conn:
        rows = await conn.fetch(_VECTOR_SQL.format(col=column), vector, CANDIDATES, DEPTH)
    return [(r["law_name"], r["article_no"]) for r in rows]


async def issue_ranking(_pool, query):
    """The answer pipeline's search: hybrid_search(official_only, issue_mode) with BM25, fusion,
    title rescue, direct lookup and MMR (Graph off). No law filter, since there is no question plan."""
    from app.services.search.hybrid_search_service import hybrid_search
    results = await hybrid_search([query], original_query=query, official_only=True, issue_mode=True)
    ranked = []
    for result in results:
        key = (result.law_name, result.article_no)
        if result.article_no and result.source_type != "interpretation" and key not in ranked:
            ranked.append(key)
    return ranked


class SwappedVectors:
    """Run the service search with another model's vectors held in memory (no database writes).

    `folder` holds docs.npy / queries.npy from evaluation/embedding_candidate.py; docs.jsonl beside it
    names each vector's article. The vector branch, its similarity threshold and the MMR vectors use
    these; BM25, fusion and lookups run as in the service. Legal interpretations have no vectors here,
    so the vector branch never returns them (the same for every model swapped in this way).
    """

    def __init__(self, folder: Path, threshold: float):
        import numpy as np
        self.np, self.threshold = np, threshold
        docs = [json.loads(line) for line in (folder.parent / "docs.jsonl").open(encoding="utf-8")]
        self.keys = [(d["law"], d["article"]) for d in docs]
        normalize = lambda m: m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-12, None)  # noqa: E731
        self.docs = normalize(np.load(folder / "docs.npy").astype(np.float32))
        self.queries = normalize(np.load(folder / "queries.npy").astype(np.float32))
        self.article_vector = {key: self.docs[i] for i, (key, d) in enumerate(zip(self.keys, docs))
                               if d["kind"] == "article"}
        self.rows, self.current = {}, None

    async def load_rows(self, pool):
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, content_hash, effective_date, law_name, law_type, tax_type, article_no, "
                "article_title, article_text, source_url FROM law_articles "
                "WHERE is_current AND law_type <> '법령해석례' ORDER BY id")
        for row in rows:
            self.rows.setdefault((row["law_name"], row["article_no"]), dict(row))

    def install(self):
        from app.services.search import hybrid_search_service as search
        swap = self

        async def cached_embed_queries(texts, *, embedder=None, diagnostics=None):
            return [swap.current.tolist() for _ in dict.fromkeys(texts)]

        async def search_law_articles(q_emb, law_filter, top_k):
            scores = swap.docs @ swap.np.asarray(q_emb, dtype=swap.np.float32)
            best = {}
            for index in swap.np.argsort(-scores)[:top_k * 4]:
                key = swap.keys[index]
                row = swap.rows.get(key)
                if row is None or key in best:
                    continue
                if law_filter != "ALL" and row["tax_type"] != law_filter:
                    continue
                best[key] = search._row_to_article_result(dict(row, similarity_score=float(scores[index])))
                if len(best) == top_k:
                    break
            return list(best.values())

        async def candidate_vectors(results):
            return {r.source_id: swap.article_vector[(r.law_name, r.article_no)] for r in results
                    if r.origin_kind == "official_law" and (r.law_name, r.article_no) in swap.article_vector}

        search.cached_embed_queries = cached_embed_queries
        search._search_law_articles = search_law_articles
        search._candidate_vectors = candidate_vectors
        search.SIMILARITY_THRESHOLD = self.threshold


async def hybrid_ranking(_pool, query):
    from app.services.search.hybrid_search_service import hybrid_search
    # A user id nobody owns: the personal-document search runs but finds nothing.
    results = await hybrid_search([query], original_query=query, user_id=PROBE_USER)
    ranked = []
    for result in results:
        key = (result.law_name, result.article_no)
        if result.article_no and result.source_type != "interpretation" and key not in ranked:
            ranked.append(key)
    return ranked


def summarize(rows):
    def block(selected):
        if not selected:
            return None
        ranks = [r["rank"] for r in selected]
        out = {"cases": len(selected)}
        for k in KS:
            out[f"hit@{k}"] = round(sum(1 for r in ranks if r and r <= k) / len(ranks), 3)
        out["mrr@20"] = round(sum(1 / r for r in ranks if r) / len(ranks), 3)
        out["median_seconds"] = round(statistics.median(r["seconds"] for r in selected), 3)
        return out

    groups = {"all": rows}
    for tier in ("colloquial", "interpretation", "legacy"):
        groups[tier] = [r for r in rows if r["tier"] == tier]
    groups["interpretation_without_article_number"] = [
        r for r in rows if r["tier"] == "interpretation" and not r["explicit_reference"]]
    return {name: block(selected) for name, selected in groups.items() if selected}


def markdown(meta, summary, rows):
    lines = [f"# Embedding retrieval probe — {meta['mode']}", "",
             f"Embedding: `{meta['embedding']}` · column `{meta['column']}` · {meta['cases']} cases · "
             f"{meta['started']}", "",
             "| Group | Cases | hit@1 | hit@5 | hit@10 | hit@20 | MRR@20 | median s |",
             "|---|---|---|---|---|---|---|---|"]
    for name, s in summary.items():
        lines.append(f"| {name} | {s['cases']} | {s['hit@1']} | {s['hit@5']} | {s['hit@10']} | {s['hit@20']} "
                     f"| {s['mrr@20']} | {s['median_seconds']} |")
    misses = [r for r in rows if not r["rank"] or r["rank"] > 10]
    lines += ["", f"## Not in the top 10 ({len(misses)})", ""]
    for r in misses:
        wanted = ", ".join(f"{a} {b}" for a, b in r["wanted"])
        found = ", ".join(f"{a} {b}" for a, b in r["top"][:3])
        lines.append(f"- `{r['id']}` rank {r['rank'] or '-'} — {r['query'][:70]} → wanted {wanted}; got {found}")
    return "\n".join(lines) + "\n"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["vector", "hybrid", "issue"], default="vector")
    parser.add_argument("--vectors", help="issue mode: a model folder from embedding_candidate.py to swap in")
    parser.add_argument("--threshold", type=float, help="issue mode with --vectors: vector similarity cut-off")
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--tier", choices=["colloquial", "interpretation", "legacy"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    from app.database import close_pool, get_pool
    from app.services.embedding_service import close_http_client

    cases = json.loads(Path(args.dataset).read_text(encoding="utf-8"))["cases"]
    if args.tier:
        cases = [c for c in cases if c["tier"] == args.tier]
    if args.limit:
        cases = cases[:args.limit]
    config.GRAPH_RAG_ENABLED = False
    rank = {"vector": vector_ranking, "hybrid": hybrid_ranking, "issue": issue_ranking}[args.mode]
    pool = await get_pool()
    swap = None
    if args.vectors:
        if args.mode != "issue":
            parser.error("--vectors works with --mode issue")
        swap = SwappedVectors(Path(args.vectors), args.threshold if args.threshold is not None
                              else config.SIMILARITY_THRESHOLD)
        all_ids = [c["id"] for c in json.loads(Path(args.dataset).read_text(encoding="utf-8"))["cases"]]
        if len(all_ids) != len(swap.queries):
            parser.error("the vectors were made for a different dataset")
        query_index = {case_id: i for i, case_id in enumerate(all_ids)}
        await swap.load_rows(pool)
        swap.install()
    fallbacks = []
    if args.mode == "issue":
        # The service builds the BM25 index at startup; a cold index times out on the first question and
        # that question falls back to another keyword search. Build it first and count any fallback.
        import logging
        from app.services.search.bm25_search_service import warm_bm25_index
        await warm_bm25_index()

        class Fallbacks(logging.Handler):
            def emit(self, record):
                if "BM25 unavailable" in record.getMessage() or "branch unavailable" in record.getMessage():
                    fallbacks.append(record.getMessage())
        logging.getLogger("app.services.search.hybrid_search_service").addHandler(Fallbacks())
    rows = []
    started = time.strftime("%Y-%m-%d %H:%M")
    try:
        for index, case in enumerate(cases, 1):
            if swap:
                swap.current = swap.queries[query_index[case["id"]]]
            begin = time.perf_counter()
            ranked = await rank(pool, case["query"])
            seconds = time.perf_counter() - begin
            wanted = targets(case)
            rows.append({"id": case["id"], "tier": case["tier"], "query": case["query"],
                         "explicit_reference": case.get("explicit_reference", False),
                         "wanted": sorted(wanted), "rank": first_hit(ranked, wanted),
                         "top": ranked[:DEPTH], "returned": len(ranked), "seconds": round(seconds, 3)})
            print(f"[{index}/{len(cases)}] {case['id']} rank={rows[-1]['rank']}", flush=True)
    finally:
        await close_http_client()
        await close_pool()

    meta = {"mode": args.mode,
            "embedding": (f"swapped:{args.vectors} threshold={swap.threshold}" if swap
                          else f"{config.EMBEDDING_PROVIDER}:{config.EMBEDDING_MODEL}"),
            "column": "embedding_v2" if config.EMBEDDING_VERSION == "v2" else "embedding",
            "cases": len(rows), "started": started, "dataset": args.dataset, "search_fallbacks": len(fallbacks)}
    summary = summarize(rows)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    (output / "report.md").write_text(markdown(meta, summary, rows), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
