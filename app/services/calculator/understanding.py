"""Answer a calculation turn from what the conversation says, and as far as the stated facts go.

Called when the regex readers could not finish (a fact they did not recognise, or an amount they left
unused). The conversation is read by the model and every fact proven against the user's words
(fact_reading); the proven facts go to the same reader as standard sentences. Then:

- the reader completes: the calculator runs, with how each fact was read listed among the assumptions;
- facts that decide the tax are still missing but each has a few possible values (조정대상지역이었는지,
  배우자가 있는지, 연·월만 말해 만 7년인지 8년인지 …): the calculator runs for every case, at most
  MAX_CASES, and the answer shows each case's tax and asks which one applies. When every case gives the
  same tax, that tax is the answer;
- an amount is missing: nothing can be computed, so the turn asks for it together with what was
  understood, and the first such turn of a calculation also gets an evidence-based explanation.

Nothing here assumes a fact. A case is labelled as a case, and its facts are the user's words or the
calculator's listed defaults.
"""
import logging
import re
from dataclasses import dataclass, replace
from datetime import date
from types import SimpleNamespace

from app.services.calculator import fact_reading

logger = logging.getLogger(__name__)
MAX_CASES = 4
TITLES = {"capital_gains": "양도소득세", "inheritance": "상속세", "gift": "증여세", "vat": "부가가치세",
          "retirement": "퇴직소득세", "income_tax": "종합소득세"}

TF = lambda field_name, yes, no: [({field_name: True}, yes), ({field_name: False}, no)]  # noqa: E731
# A fact the calculator asks (its MissingInputs label) and the cases it can take.
DIMENSIONS = {
    "capital_gains": [
        (r"취득 당시 조정대상지역", lambda r: TF("acquired_in_adjusted_area", "취득 당시 조정대상지역이었다면",
                                           "취득 당시 조정대상지역이 아니었다면")),
        (r"양도일 현재 조정대상지역", lambda r: TF("adjusted_on_transfer", "양도일 현재 조정대상지역이면",
                                            "양도일 현재 조정대상지역이 아니면")),
        (r"다주택 중과 대상인지", lambda r: TF("surcharge", "다주택 중과 대상이면", "중과 배제 주택이면")),
        (r"보유기간 중 거주기간", lambda r: [({"residence_years": 0, "lived": False}, "거주하지 않았다면"),
                                      ({"residence_years": min(r.derived["holding"])}, "보유기간 내내 거주했다면")]
         if r.derived.get("holding") else None),
        (r"1세대 1주택 여부", lambda r: TF("is_one_home", "1세대 1주택이면", "다주택이면")),
        (r"대주주인지", lambda r: [({"major_shareholder": False}, "대주주가 아니면"), ({"major_shareholder": True}, "대주주이면")]),
        (r"국내 상장주식인지", lambda r: [({"stock_market": m}, f"{m} 주식이면".replace("국외 주식", "해외 주식"))
                                     for m in ("국내상장", "국내비상장", "국외")]),
    ],
    "inheritance": [
        (r"배우자가 상속인인지", lambda r: TF("has_spouse", "배우자가 살아 있으면", "배우자가 없으면")),
        # One and three children bracket the tax (일괄공제·배우자 법정상속분); the answer asks the number.
        (r"자녀 수", lambda r: [({"children_count": n}, f"자녀가 {n}명이면") for n in (1, 3)]),
    ],
    "gift": [
        (r"관계\(", lambda r: [({"relation": "배우자"}, "배우자에게서 받으면"),
                              ({"relation": "직계존비속", "is_minor": False}, "부모에게서 받는 성년 자녀면"),
                              ({"relation": "직계존비속", "is_minor": True}, "부모에게서 받는 미성년 자녀면"),
                              ({"relation": "기타"}, "친족이 아닌 사람에게서 받으면")]),
        (r"미성년자인지", lambda r: [({"is_minor": False}, "받는 사람이 성년이면"), ({"is_minor": True}, "미성년자면")]),
        (r"혼인신고일 전후 2년", lambda r: TF("marriage_birth", "혼인·출산 공제(2년 이내)를 받으면", "그 기간 밖의 증여면")),
    ],
    "vat": [
        (r"일반과세자인지 간이과세자인지", lambda r: [({"is_simplified": False}, "일반과세자면"), ({"is_simplified": True}, "간이과세자면")]),
    ],
}
OPTION_ASKS = {"holding": "취득한 연월과 양도한 연월(보유기간이 만 몇 년인지 정합니다)",
               "residence": "거주를 시작하고 끝낸 연월(거주기간이 만 몇 년인지 정합니다)",
               "service": "입사·퇴사 연월(근속연수를 정합니다)"}


@dataclass
class Case:
    label: str
    calculation: object   # CalcRun


def _dimension(tool, label, r):
    for pattern, cases in DIMENSIONS.get(tool, ()):
        if re.search(pattern, label):
            return cases(r)
    return None


async def _reader(tool, text, history):
    """The tool's reader on the standard sentences, as the latest turn after the conversation."""
    if tool == "capital_gains":
        from app.services.calculator.capital_gains_inputs import stated_capital_gains_inputs as read
    elif tool == "inheritance":
        from app.services.calculator.inheritance_inputs import stated_inheritance_inputs as read
    elif tool == "gift":
        from app.services.calculator.gift_inputs import stated_gift_inputs as read
    elif tool == "vat":
        from app.services.calculator.vat_inputs import stated_vat_inputs as read
    elif tool == "retirement":
        from app.services.calculator.retirement_inputs import stated_retirement_inputs as read
    else:
        from app.services.calculator.income_tax_inputs import stated_income_tax_inputs
        from app.services.calculator.repository import get_deduction
        row = await get_deduction("소득세", "기본공제")
        return stated_income_tax_inputs(text, history, basic_deduction=int(row["amount"]))
    return read(text, history)


EVENT_DATES = {"capital_gains": ("transfer_date", "양도일"), "gift": ("gift_date", "증여일"),
               "inheritance": ("death_date", "상속개시일"), "retirement": ("service_end", "퇴직일")}


def event_date(tool, facts, today):
    """(date, note) of the taxed event from a proven date, or None: it decides the law that applies."""
    name, label = EVENT_DATES.get(tool, (None, None))
    value = facts.get(name)
    if not value or value == "now":
        return None
    first, last = fact_reading.period(value, today)
    note = f"{label} {last.isoformat()}에 시행된 세법으로 계산했습니다."
    return last, note + ("" if first == last else " 날짜를 정확히 말하지 않아 그 기간의 마지막 날을 기준으로 했습니다.")


async def _calculate(tool, stated, texts, facts_query, history, dated=None):
    """CalcRun for StatedInputs, with the law of the taxed event's date; None when the calculator refuses."""
    from app.services.calculator.engine import run_calculation
    from app.services.calculator.errors import CalculationError
    from app.services.calculator.tax_date import stated_tax_date
    from app.services.tools.planner import _with_penalty
    stated = _with_penalty(stated, facts_query, history)
    if stated is None or hasattr(stated, "labels"):
        return stated
    dated = dated or stated_tax_date(tool, list(texts))
    if dated and dated[0] == "ambiguous":
        return SimpleNamespace(labels=[f"어느 날짜 기준인지({dated[1]}가 둘 이상 나옵니다)"])
    if dated:
        stated = replace(stated, params={**stated.params, "as_of": dated[0]}, assumptions=[*stated.assumptions, dated[1]])
    try:
        run = await run_calculation(tool, stated.params)
    except (CalculationError, ValueError, KeyError, TypeError) as exc:
        logger.info("%s calculator not used on the read facts (%s)", tool, type(exc).__name__)
        return None
    run.context = "\n".join(["계산에 쓴 가정:", *[f"- {item}" for item in stated.assumptions], "", run.context])
    run.assumptions = tuple(stated.assumptions)
    return run


def _texts(query, history):
    return [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-2:] + [query]


def last_asked(history):
    """What the calculator asked in the previous turn (stored with that reply)."""
    if history and history[-1].get("role") == "assistant":
        return list(history[-1].get("calculator_asked") or ())
    return []


async def understood_calculation(query, history, *, conversation=None, tool_hint=None, today=None):
    """ToolRun for this calculation turn from the read facts, or None to leave the turn to the old path.

    `query` and `history` are what the readers see (a reply already joined with the question it
    answers); `conversation` is (history, message) as written, which the model reads and the proofs check.
    """
    from app.services.tools.executor import ToolRun
    today = today or date.today()
    talk_history, talk_query = conversation or (history, query)
    asked = last_asked(talk_history)
    read = await fact_reading.read_facts(talk_query, talk_history, asked=asked, tool_hint=tool_hint, today=today)
    if read is None:
        return None
    users = [str(m.get("content", "")) for m in (talk_history or [])[-8:] if m.get("role") == "user"] + [talk_query]
    proven = fact_reading.prove(read, users, asked, today)
    if proven.rejected:
        logger.info("Read facts not supported by the user's words: %s",
                    [(f, reason) for f, _, _, reason in proven.rejected])
    tool = proven.tool
    if tool == "none":
        return None
    from app.services.calculator.tax_date import stated_tax_date
    texts = _texts(query, history)
    dated = stated_tax_date(tool, texts) if tool == "capital_gains" else None
    transfer = dated[0] if dated and dated[0] != "ambiguous" else None
    base = fact_reading.reading(proven, transfer=transfer, today=today)
    # A public fact the designation record cannot settle (or a company's listing) is looked up on official
    # sites before it becomes a case or a question; the note names the page.
    from app.services.calculator import public_facts
    try:
        found = await public_facts.resolve(proven, base, today)
    except Exception as exc:
        logger.warning("Public fact lookup unavailable (%s)", type(exc).__name__)
        found = public_facts.Found()
    if found.facts:
        proven = replace(proven, facts={**proven.facts, **found.facts})
        base = fact_reading.reading(proven, transfer=transfer, today=today)
    reader_history = [*(history or []), {"role": "user", "content": query}]

    async def evaluate(assign):
        r = base if not assign else fact_reading.reading(
            replace(proven, facts={**proven.facts, **assign}), transfer=transfer, today=today)
        stated = await _reader(tool, r.text(), reader_history)
        return r, stated

    # Breadth-first over the open facts. A leaf is (facts assumed for the case, its labels, what to ask).
    leaves, done, open_leaves = [({}, [], [])], [], []
    while leaves:
        assign, labels, asks = leaves.pop(0)
        r, stated = await evaluate(assign)
        if stated is None:
            if not assign:
                return None   # A case this reader does not handle: keep the old path (formula, ask).
            continue
        if not hasattr(stated, "labels"):
            pending = [key for key in r.options if not any(k in assign for a, _ in r.options[key] for k in a)]
            if pending and len(done) + len(leaves) + len(r.options[pending[0]]) <= MAX_CASES:
                ask = OPTION_ASKS.get(pending[0], pending[0])
                leaves += [({**assign, **a}, [*labels, label], [*asks, ask]) for a, label in r.options[pending[0]]]
                continue
            done.append((labels, asks, replace(stated, assumptions=[*r.notes, *found.notes, *stated.assumptions])))
            continue
        cases = _dimension(tool, stated.labels[0], r) if len(stated.labels) <= 2 and len(labels) < 3 else None
        if cases and len(done) + len(leaves) + len(cases) <= MAX_CASES:
            leaves += [({**assign, **a}, [*labels, label], [*asks, stated.labels[0]]) for a, label in cases]
        else:
            open_leaves.append((labels, [*asks, *stated.labels]))

    runs = []
    for labels, asks, stated in done:
        run = await _calculate(tool, stated, texts, query, history, dated=event_date(tool, proven.facts, today))
        if run is not None and not hasattr(run, "labels"):
            runs.append(Case(" · ".join(labels), run))
    asked_now = list(dict.fromkeys(a for *_, asks, _ in done for a in asks)) + [
        a for _, asks in open_leaves for a in asks]
    asked_now = list(dict.fromkeys(asked_now))
    if not runs:
        missing = list(dict.fromkeys(a for _, asks in open_leaves for a in asks)) or [*base.unclear]
        if not missing:
            return None
        return ToolRun(tool, "needs_input", _ask_text(tool, base, missing), error_code="calculation_inputs_required",
                       asked=tuple(missing), understood=tuple(base.understood()), question=query)
    first = runs[0].calculation
    if len(runs) == 1 and not open_leaves and not runs[0].label:
        return ToolRun(tool, "ok", "", first)
    if len({case.calculation.result.final_tax for case in runs}) == 1 and not open_leaves:
        # Every case gives the same tax: that is the answer. The open facts stay asked, so stating one
        # later recalculates instead of starting over.
        first.assumptions = (*first.assumptions,
                             "다음 사실은 확인하지 못했지만 어느 경우든 세액이 같습니다: " + ", ".join(asked_now)
                             + f". 아래 계산표는 '{runs[0].label}'인 경우입니다.")
        return ToolRun(tool, "ok", "", first, asked=tuple(asked_now))
    first.scenarios = tuple(runs)
    first.asked = tuple(asked_now)
    first.unresolved = tuple(f"{' · '.join(labels) or '그 밖의 경우'}: {', '.join(asks)}" for labels, asks in open_leaves)
    return ToolRun(tool, "ok", "", first, asked=tuple(asked_now))


def _ask_text(tool, base, labels):
    title = TITLES.get(tool, "세액")
    understood = base.understood()
    lines = []
    if understood:
        lines += [f"{title} 계산에 쓸 사실로 지금까지 이렇게 이해했습니다:", *[f"- {item}" for item in understood], ""]
    lines.append(f"정확한 {title}을(를) 계산하려면 다음 사실을 알려주세요: " + ", ".join(labels) + ".")
    return "\n".join(lines)
