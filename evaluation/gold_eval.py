"""Run the answer pipeline on official-answer questions and compare its conclusion with the official reply.

Each case goes through the real chat path (evaluation.auto_pipeline.observe_chat: question only, no history,
no stored conversation) with its own interpretation hidden from search. A judge model then reads the
question, the official reply and the system's answer and says whether the system's conclusion agrees,
contradicts, only partly agrees, or gives none. The answer's risk features are recorded with the outcome so
evaluation/abstention_calibration.py can choose a flagging threshold.

Paid: about 6-10 pipeline calls and 1 judge call per case. Without --yes-paid it prints the plan and stops.
Results are appended to <output>/results.jsonl, so a stopped run resumes where it ended.

    python evaluation/gold_eval.py --split dev --limit 10 --output evaluation/runs/gold/<name>
    python evaluation/gold_eval.py --split dev --limit 10 --output evaluation/runs/gold/<name> --yes-paid

GOLD_JUDGE_MODEL (an OpenRouter model id) sets a judge from another family than the answer model; without it
the judge is the service's answer_judge task and the report says so (same family judges are lenient).
"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402

DATASET = Path(__file__).resolve().parent / "datasets" / "interpretation_gold.json"
OUTCOMES = ("agree", "partial", "contradict", "no_conclusion")
CALLS_PER_CASE = (7, 11)

JUDGE_PROMPT = """너는 세무 답변 채점자다. 질문에 대한 공식 회답(법제처 법령해석, 정답)과 시스템 답변을 비교한다.
시스템 답변이 질문의 핵심 쟁점에 대해 내린 결론이 공식 회답의 결론과 같은지만 판정한다. 문체·길이·근거 조문 표기는 따지지 않는다.
- agree: 시스템 결론이 공식 회답과 같다.
- partial: 결론의 방향은 같지만 조건을 빠뜨렸거나 일부 쟁점만 같다, 또는 조건부로만 같은 결론을 낸다.
- contradict: 시스템 결론이 공식 회답과 반대이거나 양립할 수 없다.
- no_conclusion: 시스템이 판단을 보류했거나 이 쟁점에 대한 결론이 없다.
answer_quote에는 시스템 답변에서 결론을 담은 문장을 그대로 복사한다(no_conclusion이면 빈 문자열).
reason에는 한두 문장으로 판정 이유를 쓴다."""

JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["outcome", "answer_quote", "reason"],
    "properties": {"outcome": {"type": "string", "enum": list(OUTCOMES)},
                   "answer_quote": {"type": "string"}, "reason": {"type": "string"}},
}


def judge_settings() -> dict:
    model = os.getenv("GOLD_JUDGE_MODEL", "").strip()
    answer_model = config.LLM_TASK_SETTINGS["answer"].model
    if model:
        return {"model": model, "provider": "openrouter", "same_family_as_answer": model.split("/")[0] == answer_model.split("/")[0]}
    judge = config.LLM_TASK_SETTINGS["answer_judge"]
    return {"model": judge.model, "provider": judge.provider, "same_family_as_answer": True}


async def call_judge(messages):
    model = os.getenv("GOLD_JUDGE_MODEL", "").strip()
    if not model:
        from app.services.llm_client import call_llm_structured
        return await call_llm_structured(messages, JUDGE_SCHEMA, temperature=0, max_tokens=1500, purpose="answer_judge")
    from app.services.inference.llm.factory import create_llm_provider
    provider = create_llm_provider("openrouter", base_url="https://openrouter.ai/api/v1", api_key=config.OPENROUTER_API_KEY,
                                   model=model, timeout=120, thinking=False)
    try:
        return await provider.structured(messages, JUDGE_SCHEMA, 0, 1500)
    finally:
        await provider.close()


def validate_judgement(result: dict, answer: str) -> dict:
    if result.get("outcome") not in OUTCOMES:
        raise ValueError("judge_outcome")
    quote = (result.get("answer_quote") or "").strip()
    if result["outcome"] != "no_conclusion" and (not quote or quote not in answer):
        raise ValueError("judge_quote_not_in_answer")
    return result


async def judge(case, answer, *, call=call_judge):
    if not answer.strip():
        return {"outcome": "no_conclusion", "answer_quote": "", "reason": "답변 없음"}
    messages = [{"role": "system", "content": JUDGE_PROMPT},
                {"role": "user", "content": json.dumps({"question": case["question"],
                                                        "official_answer": case["official_answer"],
                                                        "system_answer": answer}, ensure_ascii=False)}]
    for attempt in range(2):
        try:
            return validate_judgement(await call(messages), answer)
        except ValueError as error:
            if attempt:
                return {"outcome": "error", "answer_quote": "", "reason": str(error)}
            messages.append({"role": "user", "content": "answer_quote는 시스템 답변의 문장을 글자 그대로 복사해야 합니다. 다시 판정하세요."})


def key_article_found(case, observation) -> bool:
    wanted = {(a["law"], a["article"]) for a in case["key_articles"]}
    frames = observation.get("generation") or observation.get("contexts", [])
    found = {(r.get("law_name"), r.get("reference")) for frame in frames for r in frame.get("records", [])}
    return bool(wanted & found)


def figure_flags(verification) -> list[dict]:
    """Claims the figure check flagged, with the Judge's verdict on each (to measure wrong flags)."""
    verdicts = {row.get("claim_id"): row.get("verdict") for row in ((verification.get("judge") or {}).get("claims") or [])}
    return [{"claim_id": c["id"], "released": c.get("released"), "judge": verdicts.get(c["id"])}
            for c in verification.get("claims") or []
            if "figure_not_in_source" in (c.get("signals") or []) + (c.get("errors") or [])]


def record(case, observation, judgement) -> dict:
    from app.services.answer_risk import SCORES, risk_features
    verification = observation.get("verification") or {}
    features = risk_features(verification) if verification else None
    abstained = verification.get("status") == "withheld" or not (observation.get("answer") or "").strip()
    outcome = "no_conclusion" if abstained else judgement["outcome"]
    coverage = verification.get("coverage") or {}
    return {
        "id": case["id"], "split": case["split"], "official_verdict": case["verdict"], "outcome": outcome,
        "judge": judgement, "status": verification.get("status"), "error": observation.get("error"),
        "elapsed_seconds": round(observation.get("elapsed_seconds") or 0, 1),
        "key_article_found": key_article_found(case, observation),
        "coverage": {key: (state or {}).get("status") for key, state in coverage.items()},
        "missing_requirements": [m for state in coverage.values()
                                 for m in (state or {}).get("missing_requirements", []) or []][:10],
        "risk_features": features,
        "risk_scores": {name: round(score(features), 4) for name, score in SCORES.items()} if features else None,
        "figure_flags": figure_flags(verification),
        "answer": observation.get("answer", ""),
    }


def summarize(rows) -> dict:
    out = {}
    for split in sorted({r["split"] for r in rows}) + ["all"]:
        chosen = [r for r in rows if split in ("all", r["split"])]
        counts = {o: sum(r["outcome"] == o for r in chosen) for o in (*OUTCOMES, "error")}
        answered = counts["agree"] + counts["partial"] + counts["contradict"]
        flags = [f for r in chosen for f in r["figure_flags"]]
        out[split] = {
            "cases": len(chosen), **counts,
            "wrong_conclusion_rate": round(counts["contradict"] / len(chosen), 3) if chosen else None,
            "answer_rate": round(answered / len(chosen), 3) if chosen else None,
            "accuracy_when_answered": round(counts["agree"] / answered, 3) if answered else None,
            "key_article_recall": round(sum(r["key_article_found"] for r in chosen) / len(chosen), 3) if chosen else None,
            "figure_flags": len(flags),
            "figure_flags_on_supported_claims": sum(f["judge"] == "supported" for f in flags),
            "median_seconds": sorted(r["elapsed_seconds"] for r in chosen)[len(chosen) // 2] if chosen else None,
        }
    return out


async def run(cases, output: Path, *, observe=None, call=call_judge):
    from app.services.search.hybrid_search_service import EXCLUDED_INTERPRETATIONS
    if observe is None:
        from evaluation.auto_pipeline import observe_chat as observe
    output.mkdir(parents=True, exist_ok=True)
    path = output / "results.jsonl"
    done = {json.loads(line)["id"] for line in path.open(encoding="utf-8")} if path.exists() else set()
    for index, case in enumerate(cases, 1):
        if case["id"] in done:
            continue
        token = EXCLUDED_INTERPRETATIONS.set(frozenset({case["interpretation"]}))
        try:
            observation = await observe(case["question"])
        finally:
            EXCLUDED_INTERPRETATIONS.reset(token)
        judgement = await judge(case, observation.get("answer") or "", call=call)
        row = record(case, observation, judgement)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[{index}/{len(cases)}] {case['id']} {row['outcome']} status={row['status']} "
              f"{row['elapsed_seconds']}s", flush=True)
    rows = [json.loads(line) for line in path.open(encoding="utf-8")]
    summary = {"judge": judge_settings(), "summary": summarize(rows), "generated_at": time.strftime("%Y-%m-%d %H:%M")}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def select(dataset, split, limit, ids=()):
    cases = [c for c in dataset["cases"] if c["validity"] == "unchanged" and split in ("all", c["split"])]
    if ids:
        cases = [c for c in cases if c["id"] in ids]
    return cases[:limit] if limit else cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ids", nargs="*", default=[])
    parser.add_argument("--output", required=True)
    parser.add_argument("--yes-paid", action="store_true", help="실제 유료 모델 호출을 허용한다")
    args = parser.parse_args()
    cases = select(json.loads(Path(args.dataset).read_text(encoding="utf-8")), args.split, args.limit, set(args.ids))
    plan = {"cases": len(cases), "estimated_calls": [len(cases) * n for n in CALLS_PER_CASE],
            "judge": judge_settings(), "answer_model": config.LLM_TASK_SETTINGS["answer"].model}
    print(json.dumps(plan, ensure_ascii=False))
    if not args.yes_paid:
        print("유료 호출 전이라 멈췄습니다. 실행하려면 --yes-paid를 붙이세요.")
        return

    async def go():
        from app.database import close_pool
        from app.services.embedding_service import close_http_client
        from app.services.llm_client import close_llm_client
        from app.services.search.bm25_search_service import warm_bm25_index
        # The service's own settings (Graph included: start Neo4j first when GRAPH_RAG_ENABLED is on).
        await warm_bm25_index()
        try:
            return await run(cases, Path(args.output))
        finally:
            await close_llm_client()
            await close_http_client()
            await close_pool()
    print(json.dumps(asyncio.run(go()), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
