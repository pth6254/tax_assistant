"""Which release checks catch injected errors, measured on stored clean claims.

A seed is a claim from a stored automatic run that passes every current check on
the evidence captured with it. Deterministic mutations inject one known error
each and the current checks run again. With judge=True the claim Judge also sees
every seed and mutant (real model calls). A check that catches errors the Judge
misses earns its blocking gate; one that only repeats the Judge while also
blocking correct claims (see block_report) is a candidate to demote. Mutations
are synthetic: the counts rank checks for review, they do not certify accuracy.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from app.schemas.reliability import AnswerDraft, AnswerClaim, EvidenceRecord, QuestionPlan
from app.services import claim_verification as claims
from app.services.evidence import EvidenceContext
from app.services.law.reference_parser import reference_spans
from evaluation.block_report import block_report, load_experiments

OTHER_TAX = {"소득세법": "이 소득은 법인세 손금에도 산입됩니다.",
             "법인세법": "이 금액은 부가가치세 매입세액으로도 공제됩니다.",
             "부가가치세법": "이 비용은 법인세 손금에도 산입됩니다."}
JUDGE_ONLY = {"flipped_conclusion", "dropped_exception", "wrong_evidence"}


def _text(claim, text):
    return claim.model_copy(update={"text": text})


def unsupported_article(claim, ctx):
    law = ctx.records[0].law_name if ctx.records else "소득세법"
    return _text(claim, f"{law} 제999조에 따라 " + claim.text)


def shifted_article(claim, ctx):
    for span, reference in reference_spans(claim.text):
        if reference.article is None:
            continue
        shifted = span.replace(f"제{reference.article}조", f"제{reference.article + 1}조", 1)
        if shifted != span:
            return _text(claim, claim.text.replace(span, shifted, 1))
    return None


def invented_tax_amount(claim, ctx):
    return _text(claim, claim.text + " 따라서 납부할 세액은 1,234,567원입니다.")


def tampered_quote(claim, ctx):
    if not claim.citations:
        return None
    citations = [c.model_copy(update={"quote": c.quote + " 다만 예외 없이 적용한다."}) if n == 0 else c
                 for n, c in enumerate(claim.citations)]
    return claim.model_copy(update={"citations": citations})


def other_tax_scope(claim, ctx):
    issue = next((i for i in ctx.plan.issues if i.id == claim.issue_id), None)
    sentence = OTHER_TAX.get(issue.law) if issue else None
    return _text(claim, claim.text + " " + sentence) if sentence else None


def other_subject(claim, ctx):
    issue = next((i for i in ctx.plan.issues if i.id == claim.issue_id), None)
    others = [i.subject for i in ctx.plan.issues if re.fullmatch(r"[A-Z]", i.subject or "")
              and issue and i.subject != issue.subject]
    if not issue or not others or not re.search(rf"\b{issue.subject}", claim.text):
        return None
    return _text(claim, re.sub(rf"\b{issue.subject}(?=[가-힣])", others[0], claim.text))


def flipped_conclusion(claim, ctx):
    for old, new in (("하지 않습니다", "합니다"), ("없습니다", "있습니다"), ("않습니다", "습니다"),
                     ("있습니다", "없습니다"), ("됩니다", "되지 않습니다")):
        if old in claim.text:
            return _text(claim, claim.text.replace(old, new, 1))
    return None


def dropped_exception(claim, ctx):
    kept = re.sub(r"\s*다만[^.]*\.", "", claim.text, count=1)
    return _text(claim, kept) if kept != claim.text and kept.strip() else None


def wrong_evidence(claim, ctx):
    cited = {c.evidence_id for c in claim.citations}
    other = next((r for r in ctx.records if r.id not in cited and claims.is_official(r)
                  and any(line.strip() for line in r.text.splitlines())), None)
    if other is None or not claim.citations:
        return None
    line = next(line for line in other.text.splitlines() if line.strip())
    return claim.model_copy(update={"citations": [claim.citations[0].model_copy(
        update={"evidence_id": other.id, "quote": line})]})


MUTATIONS = {fn.__name__: fn for fn in (
    unsupported_article, shifted_article, invented_tax_amount, tampered_quote, other_tax_scope,
    other_subject, flipped_conclusion, dropped_exception, wrong_evidence)}


def load_questions(cards):
    if not cards:
        return {}
    from evaluation.auto_cards import load_cards
    return {card.id: card.draft.question for card in load_cards(cards).cards}


def seeds(experiments, questions):
    """Code-clean claims with the evidence, plan and question they were generated with."""
    seen = set()
    for path, experiment in experiments:
        for record in experiment.get("records", []):
            observation = record.get("observation") or {}
            frames = observation.get("contexts") or []
            if not frames or not frames[0].get("plan"):
                continue
            plan = QuestionPlan.model_validate(frames[0]["plan"])
            coverage = frames[0].get("coverage") or {}
            query = questions.get(record["case_id"]) or " ".join(
                [*plan.assumptions, *(i.request_quote for i in plan.issues)])
            for frame in observation.get("generation") or []:
                records = [EvidenceRecord.model_validate(r) for r in frame.get("records", [])]
                ctx = EvidenceContext("", records, plan=plan, coverage=coverage)
                for raw in (frame.get("draft") or {}).get("claims", []):
                    claim = AnswerClaim.model_validate({**raw, "depends_on": []})
                    key = hashlib.sha256(json.dumps([claim.text, [c.model_dump() for c in claim.citations]],
                                                    ensure_ascii=False).encode()).hexdigest()
                    if key in seen or claim.kind == "fact":
                        continue
                    if claims.check_claims(AnswerDraft(claims=[claim]), ctx, query)[claim.id]:
                        continue
                    seen.add(key)
                    yield {"experiment": path, "case_id": record["case_id"], "claim": claim,
                           "context": ctx, "query": query}


async def judge_supported(seed, claim):
    report, error = await claims.judge_claims(seed["query"], AnswerDraft(claims=[claim]), seed["context"])
    if report is None:
        return None, error
    row = report.claims[0]
    return row.support == row.applicability == "supported", error


async def measure(seeds_list, judge=False):
    rows, seed_judge = [], Counter()
    for seed in seeds_list:
        if judge:
            supported, _ = await judge_supported(seed, seed["claim"])
            seed_judge["supported" if supported else "error" if supported is None else "not_supported"] += 1
        for name, mutate in MUTATIONS.items():
            mutant = mutate(seed["claim"], seed["context"])
            if mutant is None:
                continue
            codes = list(dict.fromkeys(
                claims.check_claims(AnswerDraft(claims=[mutant]), seed["context"], seed["query"])[mutant.id]))
            row = {"mutation": name, "case_id": seed["case_id"], "claim_id": mutant.id,
                   "block_codes": [c for c in codes if c not in claims.SIGNAL_CHECKS],
                   "signal_codes": [c for c in codes if c in claims.SIGNAL_CHECKS]}
            if judge:
                supported, error = await judge_supported(seed, mutant)
                row["judge"] = "error" if supported is None else "supported" if supported else "rejected"
            rows.append(row)
    return rows, seed_judge


def summarize(rows, seed_count, seed_judge, judged, false_blocks):
    by_mutation = {}
    for name in MUTATIONS:
        subset = [r for r in rows if r["mutation"] == name]
        entry = Counter(applied=len(subset))
        for row in subset:
            code = bool(row["block_codes"])
            entry["caught_by_block_code"] += code
            entry["signalled_only"] += bool(row["signal_codes"]) and not code
            if judged:
                judge = row["judge"] == "rejected"
                entry["caught_by_judge"] += judge
                entry["only_code"] += code and row["judge"] == "supported"
                entry["only_judge"] += judge and not code
                entry["missed"] += not code and row["judge"] == "supported"
                entry["judge_error"] += row["judge"] == "error"
            else:
                entry["not_caught_by_code"] += not code
        by_mutation[name] = {"judge_only_by_design": name in JUDGE_ONLY, **entry}
    per_code = defaultdict(lambda: Counter(catches=0, unique_catches=0))
    for row in rows:
        for code in row["block_codes"] + row["signal_codes"]:
            per_code[code]["catches"] += 1
            per_code[code]["unique_catches"] += judged and row["judge"] == "supported"
    codes = set(per_code) | set(false_blocks)
    return {
        "note": ("합성 변형에 대한 진단입니다. Judge는 독립 세무 정답이 아니며, 수치는 검사 항목의 점검 순서를 "
                 "정하는 근거이지 정확성 입증이 아닙니다."),
        "seeds": seed_count,
        "seed_judge": dict(seed_judge) if judged else "not_run",
        "mutants": len(rows),
        "by_mutation": by_mutation,
        "by_code": sorted(({"code": code, "gate": claims.CHECKS[code].gate if code in claims.CHECKS else "unknown",
                            **per_code[code], "false_block_candidates": false_blocks.get(code, 0)}
                           for code in codes),
                          key=lambda item: (-item["catches"], item["code"])),
    }


async def filter_report(paths, *, cards=None, judge=False):
    experiments = load_experiments(paths)
    seed_list = list(seeds(experiments, load_questions(cards)))
    if judge:
        from langsmith import tracing_context
        from evaluation.adapters import close_live_clients
        try:
            with tracing_context(enabled=False):
                rows, seed_judge = await measure(seed_list, judge=True)
        finally:
            await close_live_clients()
    else:
        rows, seed_judge = await measure(seed_list)
    blocks = block_report(paths)
    false_blocks = {row["code"]: row["sole_blocker"] for row in blocks["by_code"]}
    report = summarize(rows, len(seed_list), seed_judge, judge, false_blocks)
    report["experiments"] = [path for path, _ in experiments]
    report["question_source"] = "cards" if cards else "plan_request_quotes"
    return report
