"""Compare embedding models on the statute retrieval set with one exact scorer.

Every model sees the same documents (the current statute articles and clauses, each with the input text
its stored v1 vector was built from) and the same questions, and is ranked by exact cosine over all of
them (a clause hit counts as its article; interpretations are left out). Steps:

    # 1. project venv: documents, questions, and the stored Qwen vectors as the baseline
    python evaluation/embedding_candidate.py export --output evaluation/runs/embedding-candidates
    # 2. any venv with the candidate model: evaluation/embedding_encode.py writes <name>/{docs,queries}.npy
    # 3. project venv: score each model directory
    python evaluation/embedding_candidate.py score --run evaluation/runs/embedding-candidates --model qwen4b

No writes to the database. The baseline query vectors come from the service's embedding client.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from evaluation import embedding_probe as probe  # noqa: E402

_DOCS_SQL = """
SELECT 'article' AS kind, a.id, a.law_name, a.law_type, a.tax_type, a.article_no, a.article_title,
       a.article_text, NULL::text AS clause_text, a.embedding::text AS stored
FROM law_articles a
WHERE a.is_current AND a.law_type <> '법령해석례'
UNION ALL
SELECT 'clause', c.id, a.law_name, a.law_type, a.tax_type, a.article_no, a.article_title,
       a.article_text, c.clause_text, c.embedding::text
FROM law_article_clauses c JOIN law_articles a ON a.id = c.article_id
WHERE a.is_current AND a.law_type <> '법령해석례'
ORDER BY 1, 2
"""


def input_text(row) -> str:
    from types import SimpleNamespace
    from app.services.law.clause_splitter import build_clause_embed_text
    from app.services.law.ingestion_service import _build_embed_text
    if row["kind"] == "article":
        fields = ("law_name", "law_type", "article_no", "article_title", "article_text")
        return _build_embed_text(SimpleNamespace(**{k: row[k] for k in fields}), row["tax_type"])
    return build_clause_embed_text(row["law_name"], row["article_no"], row["article_title"],
                                   row["article_text"], row["clause_text"])


async def export(run: Path, dataset: Path):
    from app.database import close_pool, get_pool
    from app.services.embedding_service import close_http_client, embed_texts
    from app.services.search.hybrid_search_service import _embedding_queries

    run.mkdir(parents=True, exist_ok=True)
    cases = json.loads(dataset.read_text(encoding="utf-8"))["cases"]
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(_DOCS_SQL)
        stored = [r for r in rows if r["stored"]]
        with (run / "docs.jsonl").open("w", encoding="utf-8") as out:
            for r in stored:
                out.write(json.dumps({"law": r["law_name"], "article": r["article_no"], "kind": r["kind"],
                                      "text": input_text(r)}, ensure_ascii=False) + "\n")
        with (run / "queries.jsonl").open("w", encoding="utf-8") as out:
            for case in cases:
                out.write(json.dumps({"id": case["id"], "query": case["query"]}, ensure_ascii=False) + "\n")
        baseline = run / "qwen4b"
        baseline.mkdir(exist_ok=True)
        np.save(baseline / "docs.npy", np.array([json.loads(r["stored"]) for r in stored], dtype=np.float32))
        queries = [c["query"] for c in cases]
        vectors = []
        for start in range(0, len(queries), 32):
            vectors += await embed_texts(_embedding_queries(queries[start:start + 32]))
        np.save(baseline / "queries.npy", np.array(vectors, dtype=np.float32))
        (baseline / "model.json").write_text(json.dumps(
            {"model": "ollama qwen3-embedding:4b (Q4_K_M), stored v1 vectors",
             "query_prompt": "Qwen instruction from hybrid_search_service._embedding_queries"}), encoding="utf-8")
        print(json.dumps({"docs": len(stored), "skipped_without_vector": len(rows) - len(stored),
                          "queries": len(queries)}))
    finally:
        await close_http_client()
        await close_pool()


def normalized(matrix):
    matrix = np.asarray(matrix, dtype=np.float32)
    return matrix / np.clip(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12, None)


def score(run: Path, model: str, dataset: Path):
    cases = json.loads(dataset.read_text(encoding="utf-8"))["cases"]
    docs = [json.loads(line) for line in (run / "docs.jsonl").open(encoding="utf-8")]
    keys = [(d["law"], d["article"]) for d in docs]
    folder = run / model
    doc_vectors, query_vectors = normalized(np.load(folder / "docs.npy")), normalized(np.load(folder / "queries.npy"))
    if len(doc_vectors) != len(docs) or len(query_vectors) != len(cases):
        raise SystemExit("vector counts do not match docs.jsonl / the dataset")
    similarity = query_vectors @ doc_vectors.T
    rows = []
    for case, scores in zip(cases, similarity):
        ranked, seen = [], set()
        for index in np.argsort(-scores):
            if keys[index] not in seen:
                seen.add(keys[index])
                ranked.append(keys[index])
                if len(ranked) == probe.DEPTH:
                    break
        wanted = probe.targets(case)
        rows.append({"id": case["id"], "tier": case["tier"], "query": case["query"],
                     "explicit_reference": case.get("explicit_reference", False), "wanted": sorted(wanted),
                     "rank": probe.first_hit(ranked, wanted), "top": ranked, "returned": len(ranked),
                     "seconds": 0.0})
    info = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    meta = {"mode": "vector-exact", "embedding": info["model"], "column": f"{run.name}/{model}",
            "cases": len(rows), "started": "", "dataset": str(dataset)}
    summary = probe.summarize(rows)
    (folder / "results.json").write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    (folder / "report.md").write_text(probe.markdown(meta, summary, rows), encoding="utf-8")
    return summary


def compare(run: Path, baseline: str, candidate: str, k: int = 5):
    """Paired view: cases only one model finds in the top k (what a sign test is computed from)."""
    a = {r["id"]: r for r in json.loads((run / baseline / "results.json").read_text(encoding="utf-8"))["rows"]}
    b = {r["id"]: r for r in json.loads((run / candidate / "results.json").read_text(encoding="utf-8"))["rows"]}
    hit = lambda r: bool(r["rank"] and r["rank"] <= k)  # noqa: E731
    only_a = [i for i in a if hit(a[i]) and not hit(b[i])]
    only_b = [i for i in a if hit(b[i]) and not hit(a[i])]
    from math import comb
    n, wins = len(only_a) + len(only_b), min(len(only_a), len(only_b))
    p = min(1.0, 2 * sum(comb(n, i) for i in range(wins + 1)) / 2 ** n) if n else 1.0
    return {"k": k, f"only_{baseline}": len(only_a), f"only_{candidate}": len(only_b),
            "sign_test_p": round(p, 4), f"only_{candidate}_ids": only_b, f"only_{baseline}_ids": only_a}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "score", "compare"):
        p = sub.add_parser(name)
        p.add_argument("--run", default="evaluation/runs/embedding-candidates")
        p.add_argument("--dataset", default=str(probe.DATASET))
    sub.choices["score"].add_argument("--model", required=True)
    sub.choices["compare"].add_argument("--baseline", default="qwen4b")
    sub.choices["compare"].add_argument("--candidate", required=True)
    sub.choices["compare"].add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    run, dataset = Path(args.run), Path(args.dataset)
    if args.command == "export":
        asyncio.run(export(run, dataset))
    elif args.command == "score":
        print(json.dumps(score(run, args.model, dataset), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(compare(run, args.baseline, args.candidate, args.k), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
