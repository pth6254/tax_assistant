import asyncio

import httpx

from config import TAVILY_API_KEY

_TAVILY_URL = "https://api.tavily.com/search"
_DOMAINS    = ["nts.go.kr", "law.go.kr", "moef.go.kr"]


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
        except Exception:
            return []

    async with httpx.AsyncClient(timeout=30.0) as client:
        nested = await asyncio.gather(*[_fetch_one(client, q) for q in queries[:3]])

    results = [item for sub in nested for item in sub]
    return "\n\n---\n\n".join(results) if results else "웹 검색 결과 없음"
