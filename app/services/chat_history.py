"""A stored chat message as the conversation history the next turn sees.

Facts about a turn come from its stored tool events, never from the generated prose: the archive
context of a history lookup, and which calculator asked the user for facts (so the reply continues
that calculation instead of starting a new question).
"""
import json


def history_entry(message) -> dict:
    msg = json.loads(message) if isinstance(message, str) else message
    entry = {"role": msg["role"], "content": msg["content"]}
    for tool in msg.get("tools", []):
        if tool.get("tool") == "history_lookup" and tool.get("history_context"):
            entry["history_context"] = tool["history_context"]
        if (tool.get("status") == "needs_input" and tool.get("scope") != "issue"
                and tool.get("error_code") == "calculation_inputs_required"):
            entry["calculator_request"] = tool.get("tool")
    return entry
