"""Non-sensitive smoke test for the configured chat routing model.

This checks routing contracts, not tax-answer correctness. It makes paid model calls.
"""
import asyncio
import os

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from app.services.chat_service import _classify_and_generate_queries
from app.services.llm_client import close_llm_client
from app.services.tools.planner import select_tool
from config import LLM_TASK_SETTINGS


async def main() -> int:
    for name in ("tool_selection", "query_classification"):
        settings = LLM_TASK_SETTINGS[name]
        print(f"{name}_model: {settings.provider}/{settings.model}/{settings.reasoning_effort or 'default'}")
    try:
        selection = await select_tool("종합소득세 5000만원의 세액을 계산해줘")
        valid_selection = bool(selection and selection[0] == "income_tax"
                               and selection[1].get("income") == 50000000)
        print(f"calculator_selection: {'ok' if valid_selection else 'mismatch'}")
        law, queries = await _classify_and_generate_queries("2024년과 2025년 의료비 세액공제 차이는?")
        # This fixture should produce alternatives; a one-query fallback is not a pass.
        valid_query = law in {"ALL", "소득세법"} and len(queries) >= 2
        print(f"query_classification: {'ok' if valid_query else 'mismatch'}")
        print(f"search_queries: {len(queries)}")
        return 0 if valid_selection and valid_query else 1
    finally:
        await close_llm_client()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
