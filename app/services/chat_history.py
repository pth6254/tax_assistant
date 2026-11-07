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
        if tool.get("scope") == "issue":
            continue
        # The calculator asked for facts, or answered by cases and asked which one applies: the next
        # turn continues that calculation.
        if (tool.get("status") == "needs_input" and tool.get("error_code") == "calculation_inputs_required") or (
                tool.get("status") == "ok" and tool.get("asked")):
            entry["calculator_request"] = tool.get("tool")
            if tool.get("asked"):
                entry["calculator_asked"] = list(tool["asked"])
    return entry
