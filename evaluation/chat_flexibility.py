"""Replay natural-phrasing calculation chats through the chat's tool step and score the replies.

Each case in datasets/chat_flexibility.json is sent turn by turn as the chat would: the reply to a turn is
stored the way chat_service stores it, so the next turn sees the same history (the calculator's pending
question included). Only the tool step runs: an analysis question is recorded as "analysis" without
generating the evidence answer.

Free by default: every model call is blocked and counted, so a turn that would need the model is
reported as `model_path`. `--yes-paid` lets the calls through (and counts them). The calculators read
their rate tables from the database, so run it where DATABASE_URL reaches it:

    python -m evaluation.chat_flexibility --output evaluation/runs/chat-flexibility-baseline
"""
import argparse
import asyncio
import json
from pathlib import Path

DATASET = Path(__file__).parent / "datasets" / "chat_flexibility.json"
PROBE_USER = "00000000-0000-0000-0000-000000000000"
AMOUNT_KINDS = {"amount", "scenarios"}


class PaidCallBlocked(Exception):
    """A model call in a free run."""


class CallCounter:
    def __init__(self, allow):
        self.allow, self.calls = allow, 0

    def install(self):
        from app.services import llm_client
        real = llm_client._get_provider
        counter = self

        class Counted:
            def __init__(self, purpose):
                self.purpose = purpose

            def __getattr__(self, name):
                async def call(*args, **kwargs):
                    counter.calls += 1
                    if not counter.allow:
                        raise PaidCallBlocked(self.purpose)
                    return await getattr(real(self.purpose), name)(*args, **kwargs)

                async def stream(*args, **kwargs):
                    counter.calls += 1
                    if not counter.allow:
                        raise PaidCallBlocked(self.purpose)
                    async for chunk in real(self.purpose).stream(*args, **kwargs):
                        yield chunk
                return stream if name == "stream" else call

        llm_client._get_provider = lambda purpose="answer": Counted(purpose)


readings = []   # what the model read and what its proof kept, for the turn being replayed


def record_readings():
    from app.services.calculator import fact_reading
    prove = fact_reading.prove

    def recorded(read, texts, asked=(), today=None):
        proven = prove(read, texts, asked, today)
        readings.append({"tool": read.tool, "read": [f.model_dump() for f in read.facts], "kept": proven.facts,
                         "rejected": proven.rejected})
        return proven
    fact_reading.prove = recorded


def _reply_text(run, events):
    from app.services.calculator.engine import format_calculation_answer
    from app.services import chat_service
    if run is None:
        return "(근거 검색으로 답하는 분석 질문)"
    if run.status == "ok" and run.calculation:
        return format_calculation_answer(run.calculation)
    return chat_service._failed_tool_answer(events) or run.context


def classify(run, blocked_before, counter):
    """kind, the calculator inputs and taxes of an amount reply, and the facts asked."""
    from app.services import chat_service
    asked = list(getattr(run, "asked", ()) or ())
    if run is None:
        return {"kind": "model_path" if counter.calls > blocked_before and not counter.allow else "analysis"}
    scenarios = list(getattr(run.calculation, "scenarios", ()) or ()) if run.calculation else []
    if run.status == "ok" and scenarios:
        return {"kind": "scenarios", "params": [s.calculation.params for s in scenarios],
                "taxes": [s.calculation.result.final_tax for s in scenarios], "labels": [s.label for s in scenarios],
                "asked": asked}
    if run.status == "ok" and run.calculation:
        # A single amount shows no question; facts it leaves open are kept only to continue the calculation.
        calc = run.calculation
        return {"kind": "amount", "params": [calc.params], "taxes": [calc.result.final_tax if calc.result else None],
                "open": asked, "assumptions": list(calc.assumptions)}
    if run.tool == "formula_calculation":
        return {"kind": "formula"}
    if counter.calls > blocked_before and not counter.allow:
        return {"kind": "model_path"}
    if run.status == "needs_input":
        from app.services.tools import planner
        reply = getattr(chat_service, "needs_input_reply", lambda _run: "ask_only")(run)
        labels = asked or (planner._labels(run.context) if hasattr(planner, "_labels") else [run.context])
        return {"kind": reply, "asked": labels, "understood": list(getattr(run, "understood", ()) or ())}
    return {"kind": "error", "detail": f"{run.tool}:{run.status}:{run.error_code}"}


def _matches(expected, observed):
    return observed in expected if isinstance(expected, list) else observed == expected


def score(case, turns):
    expect = case["expect"]
    by_turn = expect.get("amount_by_turn", len(case["turns"]))
    first_amount = next((i + 1 for i, t in enumerate(turns) if t["kind"] in AMOUNT_KINDS), None)
    final = turns[-1]["kind"]
    if expect["reply"] == "amount":
        reply_ok = first_amount is not None and first_amount <= by_turn
    elif expect["reply"] == "explain":
        reply_ok = final in {"explain_ask", "analysis", "amount", "scenarios"}
    else:
        reply_ok = final not in {"ask_only", "error"}
    last_amount = next((t for t in reversed(turns) if t["kind"] in AMOUNT_KINDS), None)
    params = expect.get("params", {})
    matched = {key: bool(last_amount) and all(_matches(value, p.get(key)) for p in last_amount["params"])
               for key, value in params.items()}
    tax_ok = None
    if "final_tax" in expect:
        tax_ok = bool(last_amount) and all(t == expect["final_tax"] for t in last_amount["taxes"])
    asked = [(i, label) for i, t in enumerate(turns) for label in t.get("asked", [])]
    start = expect.get("never_ask_from_turn", 1) - 1   # a fact the user gives later may be asked before it
    unneeded = [label for i, label in asked if i >= start and any(word in label for word in expect.get("never_ask", []))]
    repeated = [label for i, label in asked if (i + 1, label) in asked]
    return {"reply_ok": reply_ok, "first_amount_turn": first_amount, "params": matched, "tax_ok": tax_ok,
            "ask_only_turns": sum(t["kind"] == "ask_only" for t in turns), "unneeded_asks": unneeded,
            "repeated_asks": repeated}


async def replay(case, counter):
    from app.services import chat_service
    from app.services.chat_history import history_entry
    from app.services.tools.planner import run_tools_for_query
    stored, turns = [], []
    for text in case["turns"]:
        events = []
        keep = getattr(chat_service, "MEMORY_KEYS", ("role", "content", "calculator_request"))
        history = [{k: m[k] for k in keep if k in m} for m in stored]
        before = counter.calls
        readings.clear()
        try:
            run = await run_tools_for_query(text, user_id=PROBE_USER, history=history, on_event=events.append)
        except PaidCallBlocked:
            run, events = None, []
            turns.append({"text": text, "kind": "model_path", "calls": counter.calls - before})
        else:
            outcome = classify(run, before, counter)
            turns.append({"text": text, **outcome, "calls": counter.calls - before, "readings": list(readings)})
        stored += [{"role": "user", "content": text},
                   history_entry({"role": "assistant", "content": _reply_text(run, events),
                                  "tools": chat_service._terminal_tools(events)})]
    return turns


def summarize(results):
    def share(items):
        items = list(items)
        return f"{sum(items)}/{len(items)}"
    by_reply = {}
    for r in results:
        by_reply.setdefault(r["expect"]["reply"], []).append(r["score"]["reply_ok"])
    keys = [ok for r in results for ok in r["score"]["params"].values()]
    taxes = [r["score"]["tax_ok"] for r in results if r["score"]["tax_ok"] is not None]
    turns = [t for r in results for t in r["turns"]]
    return {
        "cases": len(results),
        "reply_ok": share(r["score"]["reply_ok"] for r in results),
        "reply_ok_by_expectation": {k: share(v) for k, v in by_reply.items()},
        "ask_only_turns": share(t["kind"] == "ask_only" for t in turns),
        "summary_ask_turns": share(t["kind"] == "summary_ask" for t in turns),
        "explain_ask_turns": share(t["kind"] == "explain_ask" for t in turns),
        "model_path_turns": share(t["kind"] == "model_path" for t in turns),
        "params_matched": share(keys),
        "tax_matched": share(taxes),
        "unneeded_asks": sum(len(r["score"]["unneeded_asks"]) for r in results),
        "repeated_asks": sum(len(r["score"]["repeated_asks"]) for r in results),
        "model_calls": sum(t.get("calls", 0) for t in turns),
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--output", required=True)
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--yes-paid", action="store_true", help="let model calls through (they are billed)")
    parser.add_argument("--rescore", help="score a saved results.json again with the current dataset (no run)")
    args = parser.parse_args()
    if args.rescore:
        cases = {c["id"]: c for c in json.loads(Path(args.dataset).read_text(encoding="utf-8"))["cases"]}
        saved = json.loads(Path(args.rescore).read_text(encoding="utf-8"))
        results = [{**r, "expect": cases[r["id"]]["expect"], "score": score(cases[r["id"]], r["turns"])}
                   for r in saved["results"] if r["id"] in cases]
        print(json.dumps(summarize(results), ensure_ascii=False, indent=2))
        return
    from app.database import close_pool, get_pool
    cases = json.loads(Path(args.dataset).read_text(encoding="utf-8"))["cases"]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    counter = CallCounter(args.yes_paid)
    counter.install()
    record_readings()
    await get_pool()
    results = []
    try:
        for case in cases:
            turns = await replay(case, counter)
            results.append({"id": case["id"], "tool": case["tool"], "expect": case["expect"], "turns": turns,
                            "score": score(case, turns)})
            s = results[-1]["score"]
            print(f"{case['id']:<22} {'OK ' if s['reply_ok'] else 'NO '} "
                  + " → ".join(t["kind"] for t in turns)
                  + (f" | params {sum(s['params'].values())}/{len(s['params'])}" if s["params"] else "")
                  + (f" | 불필요 질문 {len(s['unneeded_asks'])}" if s["unneeded_asks"] else "")
                  + (f" | 반복 질문 {len(s['repeated_asks'])}" if s["repeated_asks"] else ""), flush=True)
    finally:
        await close_pool()
    summary = summarize(results)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps({"summary": summary, "paid": args.yes_paid, "results": results},
                                                 ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
