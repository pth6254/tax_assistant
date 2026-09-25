"""Small live diagnostic for the completed historical embedding index.

These source-derived probes verify retrieval wiring, not legal answer accuracy.
No chat history is read or written.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.database import close_pool
from app.services.embedding_service import close_http_client
from app.services.search.history_search import HistoryUnavailable, retrieve


POSITIVE = (
    ("법령버전 529 소득세 납세의무를 설명해줘", 529, {"제1조", "제2조"}),
    ("법령버전 1012 양도담보권자의 물적 납세의무를 설명해줘", 1012, {"제75조"}),
    ("법령버전 1063 양도담보권자로부터 징수하는 절차를 설명해줘", 1063, {"제16조"}),
)
NEGATIVE = (
    "법령버전 529 제9999조 원문을 설명해줘",
    "2019년 지방세징수법 제16조 원문을 설명해줘",
)


async def main():
    report = {"positive": [], "negative": [], "started_at": datetime.now(timezone.utc).isoformat()}
    try:
        for query, version, expected in POSITIVE:
            try:
                result = await retrieve(query)
                primary = [r for r in result["results"] if not r["graph_evidence"]]
                hits = [r["article_no"] for r in primary]
                passed = bool(expected.intersection(hits)) and all(
                    r["version_id"] == version for r in primary
                )
                report["positive"].append({
                    "query": query, "expected": sorted(expected), "hits": hits,
                    "graph_status": result["graph_status"],
                    "graph_added": len(result["results"]) - len(primary), "passed": passed,
                })
            except Exception as exc:
                report["positive"].append({
                    "query": query, "expected": sorted(expected),
                    "error": type(exc).__name__, "passed": False,
                })
        for query in NEGATIVE:
            try:
                await retrieve(query)
                report["negative"].append({"query": query, "passed": False})
            except HistoryUnavailable as exc:
                report["negative"].append({
                    "query": query, "reason": str(exc), "passed": True,
                })
            except Exception as exc:
                report["negative"].append({
                    "query": query, "error": type(exc).__name__, "passed": False,
                })
        report["passed"] = all(x["passed"] for x in report["positive"] + report["negative"])
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        directory = Path("evaluation/runs/law-history-index")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / ("retrieval-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + ".json")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0 if report["passed"] else 1
    finally:
        await close_http_client()
        await close_pool()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    raise SystemExit(asyncio.run(main()))
