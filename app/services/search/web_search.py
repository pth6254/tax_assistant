import asyncio
import logging

import httpx

from config import TAVILY_API_KEY

logger = logging.getLogger(__name__)

_TAVILY_URL = "https://api.tavily.com/search"
_DOMAINS    = ["nts.go.kr", "law.go.kr", "moef.go.kr"]


async def web_pages(query: str, domains: list[str], max_results: int = 4) -> list[dict]:
    """[{url, content}] from the given official domains only; [] when search is off or fails."""
    if not TAVILY_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                _TAVILY_URL, headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
                json={"query": query, "search_depth": "advanced", "max_results": max_results,
                      "include_domains": domains})
            resp.raise_for_status()
            return [{"url": r.get("url", ""), "content": r.get("content", "")}
                    for r in resp.json().get("results", []) if any(d in r.get("url", "") for d in domains)]
    except Exception as exc:
        logger.warning("[WEB] Tavily search unavailable (%s)", type(exc).__name__)
        return []


async def tavily_search(queries: list[str]) -> str:
    """Tavily 웹 검색 — 최대 3개 쿼리를 병렬 실행. 결과를 포맷된 문자열로 반환."""
    async def _fetch_one(client: httpx.AsyncClient, query: str) -> list[str]:
        try:
            resp = await client.post(
                _TAVILY_URL,
                headers={"Authorization": f"Bearer {TAVILY_API_KEY}"},
                json={
                    "query":           query,
                    "search_depth":    "advanced",
                    "max_results":     3,
                    "include_domains": _DOMAINS,
                },
            )
            resp.raise_for_status()
            return [
                f"[출처: {r.get('url', '?')}]\n{r.get('content', '')[:500]}"
                for r in resp.json().get("results", [])
            ]
        except Exception as exc:
            logger.warning("[WEB] Tavily search unavailable (%s)", type(exc).__name__)
            return []

    async with httpx.AsyncClient(timeout=30.0) as client:
        nested = await asyncio.gather(*[_fetch_one(client, q) for q in queries[:3]])

    results = [item for sub in nested for item in sub]
    return "\n\n---\n\n".join(results) if results else "웹 검색 결과 없음"
