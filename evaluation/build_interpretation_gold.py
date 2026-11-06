"""Build evaluation/datasets/interpretation_gold.json: questions whose correct answer is an official reply.

Every legal interpretation stored in the database (법제처 법령해석, law_type='법령해석례') carries the question
([질의요지]), the official answer ([회답]) and the reasoning ([이유]). The official answer is the label, so the
set needs no tax expert. A case is usable for current-law evaluation only when the articles it turns on read
the same today as on the reply date: the law history archive gives each article's text over
[reply date, today], and one unchanged text means the reply still holds (validity "unchanged").

Evaluation hides the interpretation itself from search (hybrid_search_service.EXCLUDED_INTERPRETATIONS),
otherwise the system would read the answer. Cases are split into development (calibration and tuning) and
test (acceptance only) by a hash of the interpretation number, so the split never changes between builds.

    python evaluation/build_interpretation_gold.py
"""
import asyncio
import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg  # noqa: E402

import config  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "datasets" / "interpretation_gold.json"
MAX_QUESTION_CHARS = 1500
TEST_SHARE = 0.4

SECTION = re.compile(r"\[(질의요지|회답|이유)\]")
FOOTNOTE = re.compile(r"(\d+)\)\1\)[^\n]*\n?")
BACKGROUND = re.compile(r"<\s*질의\s*배경\s*>.*", re.S)
CITE = re.compile(r"「(?P<law>[^」]+)」\s*(?P<art>제\d+조(?:의\d+)?)(?:\s*제(?P<para>\d+)항)?")
TITLE_CITE = re.compile(r"\((?P<cite>「[^」]+」\s*제[^)]*)\)\s*$")
MULTI_PART = re.compile(r"^\s*(?:가\.|1\.|질의\s*가)")
YES_NO = re.compile(r"(?:지\s*\??\s*$|여부|지\?|는지|ㄴ지|할\s*수\s*있는지)")
# The reply's verdict is the predicate that ends its first sentence.
NEGATIVE = re.compile(r"(?:수\s*없습니다|않습니다|아닙니다|없습니다|불가합니다|아니합니다)\s*$")
POSITIVE = re.compile(r"(?:수\s*있습니다|합니다|됩니다|입니다|있습니다)\s*$")


def sections(text: str) -> dict:
    parts, names = SECTION.split(text), {}
    for name, body in zip(parts[1::2], parts[2::2]):
        names.setdefault(name, body.strip())
    return names


def clean_question(text: str) -> str:
    text = BACKGROUND.sub("", FOOTNOTE.sub("", text))
    return re.sub(r"\s+", " ", text).strip()


def first_sentence(text: str) -> str:
    match = re.search(r"^(.*?(?:습니다|니다))\s*[.。]", re.sub(r"\s+", " ", text).strip())
    return match[1] if match else ""


def verdict(question: str, answer: str) -> str | None:
    """'yes' / 'no' for a yes-or-no question with a single answer, otherwise None."""
    if MULTI_PART.match(answer) or not YES_NO.search(question):
        return None
    sentence = first_sentence(answer)
    if NEGATIVE.search(sentence):
        return "no"
    if POSITIVE.search(sentence):
        return "yes"
    return None


def split_of(case_id: str) -> str:
    bucket = int(hashlib.sha256(case_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if bucket < TEST_SHARE else "dev"


async def validity(conn, law: str, article: str, replied_on: date, today: date, paragraphs=()) -> str:
    """unchanged: the cited paragraphs (or the whole article) read the same from the reply date to today;
    changed: amended since; unknown: not archived."""
    from app.services.historical_evidence import archived_articles
    from app.services.law.reference_parser import extract_law_reference
    reference = extract_law_reference(f"{law} {article}")
    if not reference or reference.article is None:
        return "unknown"
    texts = await archived_articles(law, reference, replied_on, today, pool=conn)
    if not texts:
        return "unknown"
    # Amendment notes (<개정 2019.12.31>, [전문개정 …]) change with every amendment of the law; only the
    # provision's own wording decides whether the reply still holds.
    return "unchanged" if len({provision_text(paragraph_text(t.body, paragraphs)) for t in texts}) == 1 else "changed"


def paragraph_text(body: str, paragraphs) -> str:
    """The cited paragraphs (① = 1) of an article; the whole article when none is cited or found.

    Tax laws are amended every year, usually in other paragraphs than the one a reply turns on.
    """
    if not paragraphs:
        return body
    parts = {}
    for segment in re.split(r"(?=[①-⑳])", body or ""):
        if segment and "①" <= segment[0] <= "⑳":
            parts.setdefault(ord(segment[0]) - ord("①") + 1, segment)
    chosen = [parts[p] for p in sorted(paragraphs) if p in parts]
    return "\n".join(chosen) if len(chosen) == len(set(paragraphs)) else body


ANNOTATION = re.compile(r"<(?:개정|신설|삭제|타법개정|본조신설)[^>]*>|\[(?:전문개정|본조신설|제목개정|종전[^\]]*)[^\]]*\]")


def provision_text(body: str) -> str:
    return re.sub(r"\s+", "", ANNOTATION.sub("", body or ""))


async def build(today: date | None = None) -> dict:
    today = today or date.today()
    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        current = {(r["law_name"], r["article_no"]) for r in await conn.fetch(
            "SELECT law_name, article_no FROM law_articles WHERE is_current AND law_type <> '법령해석례'")}
        rows = await conn.fetch(
            "SELECT id, article_no, article_title, article_text, effective_date, source_url FROM law_articles "
            "WHERE law_type = '법령해석례' ORDER BY article_no")
        cases, skipped = [], {}

        def skip(reason):
            skipped[reason] = skipped.get(reason, 0) + 1

        for row in rows:
            parts = sections(row["article_text"] or "")
            question, answer = clean_question(parts.get("질의요지", "")), parts.get("회답", "").strip()
            if not question or not answer:
                skip("missing_question_or_answer")
                continue
            if len(question) > MAX_QUESTION_CHARS:
                skip("question_too_long")
                continue
            title_cite = TITLE_CITE.search(row["article_title"] or "")
            matches = list(CITE.finditer(
                (title_cite["cite"] if title_cite else "") + " " + question + " " + first_sentence(answer)))
            articles = [pair for pair in dict.fromkeys((m["law"], m["art"]) for m in matches) if pair in current]
            if not articles:
                skip("no_current_article")
                continue
            if not re.fullmatch(r"\d{8}", row["effective_date"] or ""):
                skip("no_reply_date")
                continue
            replied_on = datetime.strptime(row["effective_date"], "%Y%m%d").date()
            paragraphs = {pair: {int(m["para"]) for m in matches if (m["law"], m["art"]) == pair and m["para"]}
                          for pair in articles}
            states = [await validity(conn, law, art, replied_on, today, paragraphs[(law, art)])
                      for law, art in articles[:3]]
            state = ("changed" if "changed" in states else "unknown" if "unknown" in states else "unchanged")
            cases.append({
                "id": f"gold-{row['article_no']}", "interpretation": row["article_no"],
                "split": split_of(row["article_no"]), "question": question,
                "official_answer": answer, "official_reason": parts.get("이유", "")[:4000],
                "verdict": verdict(question, answer), "key_articles": [{"law": l, "article": a} for l, a in articles],
                "replied_on": replied_on.isoformat(), "validity": state, "article_validity": states,
                "source_url": row["source_url"] or ""})
    finally:
        await conn.close()
    summary = {
        "cases": len(cases), "skipped": skipped,
        "validity": {s: sum(c["validity"] == s for c in cases) for s in ("unchanged", "changed", "unknown")},
        "verdict": {str(v): sum(c["verdict"] == v for c in cases) for v in ("yes", "no", None)},
        "usable_now": {split: sum(c["validity"] == "unchanged" and c["split"] == split for c in cases)
                       for split in ("dev", "test")},
    }
    dataset = {"name": "interpretation-gold", "version": "1.0.0", "built_on": today.isoformat(),
               "description": "Questions from 법제처 legal interpretations; the official reply is the label. "
                              "Use only validity=unchanged cases for current-law evaluation.",
               "summary": summary, "cases": cases}
    OUTPUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(asyncio.run(build()), ensure_ascii=False, indent=1))
