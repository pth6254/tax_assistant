"""Non-sensitive smoke test for the configured chat routing model.

This checks the routing contract, not tax-answer correctness. It makes one paid model call. The six tax
calculators no longer use the model selection (their readers decide), so the probe asks for a tax outside
them. Search queries are planned per issue by `question_planning`, not by a chat-level classifier.
"""
import asyncio
import os

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from app.services.llm_client import close_llm_client
from app.services.tools.planner import select_tool
from config import LLM_TASK_SETTINGS


async def main() -> int:
    settings = LLM_TASK_SETTINGS["tool_selection"]
    print(f"tool_selection_model: {settings.provider}/{settings.model}/{settings.reasoning_effort or 'default'}")
    try:
        # A bare article reference is parsed without the model; a tax outside the calculators is not.
        selection = await select_tool("주택을 5억원에 취득했는데 취득세 계산해줘")
        valid_selection = bool(selection and selection[0] == "formula_calculation")
        print(f"formula_selection: {'ok' if valid_selection else 'mismatch'}")
        return 0 if valid_selection else 1
    finally:
        await close_llm_client()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
