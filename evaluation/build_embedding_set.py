"""Build evaluation/datasets/embedding_retrieval.json: questions with the statute articles that answer them.

Three tiers, kept apart in the scores because they test different things:
- colloquial: everyday wording that avoids the statute's terms. Written for this set; every label was
  checked against the stored article's title and text (not a tax expert's review).
- interpretation: the issue line of 법제처 legal interpretations stored in law_articles, with the first
  article the interpretation itself cites as the answer. Formal wording, official labels.
- legacy: the required labels of evaluation/datasets/retrieval.json (term-heavy short questions).

A label is the article (law name + article number) of the current statute. `acceptable` lists other
articles that answer the question as well; finding one counts as a hit.

Run inside the project (needs the database):
    python evaluation/build_embedding_set.py
"""
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg  # noqa: E402

import config  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "datasets" / "embedding_retrieval.json"
LEGACY = ROOT / "datasets" / "retrieval.json"

# (law, article, question, acceptable other articles)
COLLOQUIAL = [
    ("소득세법", "제12조", "월세 받는 집이 딱 한 채뿐인데 그 임대 수입에도 세금을 내야 하나요?", []),
    ("소득세법", "제16조", "은행 예금에서 받은 이자도 소득세를 내는 건가요?", []),
    ("소득세법", "제17조", "주식 갖고 있다가 받은 배당금은 어떤 소득으로 잡히나요?", []),
    ("소득세법", "제20조", "월급 말고 회사에서 받은 상여금이나 각종 수당도 근로소득에 들어가나요?", []),
    ("소득세법", "제21조", "가끔 강연하고 받은 강연료나 원고료는 무슨 소득으로 보나요?", []),
    ("소득세법", "제22조", "회사를 그만두면서 받은 퇴직금은 어떤 소득으로 분류되나요?", []),
    ("소득세법", "제52조", "전세 대출 원리금을 갚고 있는데 이것도 연말정산 때 빼주나요?", []),
    ("소득세법", "제59조의2", "아이 둘 키우는 집은 세금을 얼마나 깎아주나요?", []),
    ("소득세법", "제59조의3", "연금저축에 돈을 넣으면 연말정산에서 돌려받을 수 있나요?", []),
    ("소득세법", "제59조의4", "부모님 병원비를 제가 냈는데 연말정산 때 공제받을 수 있나요?", []),
    ("소득세법", "제70조", "프리랜서로 일했는데 5월에 따로 신고를 꼭 해야 하나요?", []),
    ("소득세법", "제73조", "회사 월급만 받는 직장인도 5월에 종합소득 신고를 해야 하나요?", []),
    ("소득세법", "제94조", "땅이나 건물을 팔아서 남긴 돈에도 세금이 붙나요? 어떤 걸 팔면 해당되나요?", []),
    ("소득세법", "제95조", "집을 오래 가지고 있다가 팔면 세금을 좀 깎아주나요?", []),
    ("소득세법", "제97조", "집 팔 때 중개수수료나 고친 비용은 차익에서 빼주나요?", []),
    ("소득세법", "제104조", "집 산 지 1년도 안 돼서 팔면 세금이 더 많이 나오나요?", []),
    ("소득세법", "제105조", "부동산을 팔고 나면 언제까지 세금 신고를 해야 하나요?", []),
    ("소득세법", "제127조", "아르바이트생 월급 줄 때 세금을 떼고 줘야 하나요?", []),
    ("소득세법 시행령", "제154조", "집 한 채를 2년 넘게 갖고 있다가 팔면 세금을 안 내도 되나요?",
     [("소득세법", "제89조")]),
    ("소득세법 시행령", "제155조", "이사하려고 새 집을 먼저 샀는데 예전 집을 팔면 세금이 면제되나요?", []),
    ("부가가치세법", "제8조", "가게를 새로 열면 사업자등록은 언제까지 해야 하나요?", []),
    ("부가가치세법", "제26조", "병원 진료비나 학원비에도 부가세가 붙나요?", []),
    ("부가가치세법", "제38조", "가게 물건 살 때 낸 부가세는 나중에 빼주나요?", []),
    ("부가가치세법", "제46조", "손님이 카드로 결제하면 가게 부가세를 깎아준다던데 맞나요?", []),
    ("부가가치세법", "제49조", "부가세는 일 년에 몇 번, 언제 신고하나요?", []),
    ("부가가치세법", "제61조", "매출이 크지 않은 작은 가게는 부가세를 간단하게 내는 방법이 있나요?", []),
    ("부가가치세법", "제69조", "1년 매출이 아주 적은 작은 가게도 부가세를 내야 하나요?", []),
    ("법인세법", "제13조", "작년에 회사가 적자였는데 그 손실을 올해 이익에서 빼줄 수 있나요?", []),
    ("법인세법", "제23조", "회사에서 산 기계 값을 몇 년에 걸쳐 비용으로 처리하나요?", []),
    ("법인세법", "제24조", "회사가 낸 기부금은 전부 비용으로 인정받을 수 있나요?", []),
    ("법인세법", "제25조", "거래처 접대하는 데 쓴 돈은 얼마까지 회사 경비로 인정되나요?", []),
    ("법인세법", "제52조", "대표이사한테 회사 건물을 시세보다 싸게 빌려주면 문제가 되나요?", []),
    ("법인세법", "제55조", "회사가 내는 법인세율은 몇 퍼센트인가요?", []),
    ("법인세법", "제60조", "법인세 신고는 사업연도가 끝나고 언제까지 해야 하나요?", []),
    ("상속세 및 증여세법", "제13조", "돌아가시기 몇 년 전에 자식에게 미리 준 재산도 상속세 계산에 들어가나요?", []),
    ("상속세 및 증여세법", "제14조", "장례식 비용이나 고인의 빚은 상속재산에서 빼주나요?", []),
    ("상속세 및 증여세법", "제19조", "남편이 돌아가셨을 때 아내가 물려받는 재산은 세금에서 얼마나 빼주나요?", []),
    ("상속세 및 증여세법", "제20조", "상속받는 사람 중에 미성년 자녀나 연로한 부모님이 있으면 공제가 늘어나나요?", []),
    ("상속세 및 증여세법", "제26조", "상속받은 재산이 많을수록 상속세율이 얼마나 올라가나요?", []),
    ("상속세 및 증여세법", "제45조", "소득이 없는 자녀 이름으로 집을 사면 증여받은 걸로 보나요?", []),
    ("상속세 및 증여세법", "제47조", "같은 사람한테 몇 년에 걸쳐 여러 번 받은 돈은 합쳐서 세금을 매기나요?", []),
    ("상속세 및 증여세법", "제53조", "부모님이 자녀에게 돈을 줄 때 얼마까지는 세금이 없나요?", []),
    ("상속세 및 증여세법", "제53조의2", "결혼할 때 부모님한테 받는 돈은 따로 더 공제해 주나요?", []),
    ("상속세 및 증여세법", "제56조", "증여받은 금액이 크면 세율이 몇 퍼센트까지 올라가나요?",
     [("상속세 및 증여세법", "제26조")]),
    ("상속세 및 증여세법", "제68조", "돈을 증여받았으면 언제까지 신고해야 하나요?", []),
    ("국세기본법", "제14조", "사업자 명의만 다른 사람 이름으로 해 두면 세금은 누가 내게 되나요?", []),
    ("국세기본법", "제26조의2", "몇 년이 지나면 세무서가 예전 세금을 더 걷어갈 수 없나요?", []),
    ("국세기본법", "제45조", "세금을 덜 신고한 걸 나중에 알았는데 어떻게 바로잡나요?", []),
    ("국세기본법", "제45조의2", "세금을 너무 많이 냈다는 걸 알았는데 돌려받을 수 있나요?", []),
    ("국세기본법", "제47조의2", "세금 신고를 아예 안 하면 벌금처럼 얼마가 더 붙나요?", []),
    ("국세기본법", "제47조의4", "세금을 늦게 내면 하루하루 이자처럼 더 붙나요?", []),
    ("국세기본법", "제55조", "세무서 처분이 억울하면 어디에 어떻게 이의를 제기하나요?", []),
    ("조세특례제한법", "제30조", "중소기업에 처음 취직한 청년은 소득세를 깎아주나요?", []),
    ("조세특례제한법", "제69조", "8년 넘게 직접 농사지은 땅을 팔면 세금이 줄어드나요?", []),
    ("조세특례제한법", "제87조", "청약통장에 넣는 돈도 연말정산 때 빼주나요?", []),
    ("조세특례제한법", "제91조의18", "ISA 계좌에서 생긴 이자나 배당에는 세금이 없나요?", []),
    ("조세특례제한법", "제100조의3", "형편이 어려운 맞벌이 부부도 근로장려금을 받을 수 있나요?", []),
    ("조세특례제한법", "제126조의2", "체크카드를 많이 쓰면 연말정산에 도움이 되나요?", []),
    ("지방세법", "제11조", "아파트를 살 때 내는 취득세율은 얼마인가요?", []),
    ("지방세법", "제20조", "집을 산 다음 취득세는 언제까지 내야 하나요?", []),
    ("지방세법", "제111조", "아파트 재산세는 몇 퍼센트로 매겨지나요?", []),
    ("지방세법", "제114조", "6월에 집을 팔면 그 해 재산세는 파는 사람과 사는 사람 중 누가 내나요?",
     [("지방세법", "제107조")]),
    ("지방세법", "제127조", "내 차 자동차세는 어떻게 계산되나요?", []),
    ("관세법", "제96조", "해외여행 가서 산 물건은 얼마까지 세금 없이 들여올 수 있나요?", []),
]

# "민원인 - <issue>(「법」 제N조제M항 등 관련)"
TITLE = re.compile(r"^(?P<asker>[^-]+?)\s*-\s*(?P<issue>.+?)\s*\((?P<cite>「[^」]+」\s*제[^)]*)\)\s*$")
CITE = re.compile(r"「(?P<law>[^」]+)」\s*(?P<art>제\d+조(?:의\d+)?)")
EXPLICIT = re.compile(r"「[^」]+」\s*제\d+조")


def article(law, art):
    return {"law": law, "article": art}


async def build():
    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        current = {(r["law_name"], r["article_no"]) for r in await conn.fetch(
            "SELECT law_name, article_no FROM law_articles WHERE is_current AND law_type <> '법령해석례'")}
        interpretations = await conn.fetch(
            "SELECT article_no, article_title FROM law_articles WHERE law_type = '법령해석례' ORDER BY article_no")
    finally:
        await conn.close()

    cases, skipped = [], {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    for index, (law, art, question, acceptable) in enumerate(COLLOQUIAL, 1):
        missing = [pair for pair in [(law, art), *acceptable] if pair not in current]
        if missing:
            raise SystemExit(f"colloquial label not in the current corpus: {missing}")
        cases.append({"id": f"col-{index:02d}", "tier": "colloquial", "query": question,
                      "required": [article(law, art)], "acceptable": [article(*a) for a in acceptable],
                      "source": "written for this set; label checked against the stored article"})

    for row in interpretations:
        match = TITLE.match(row["article_title"] or "")
        if not match:
            skip("title_without_issue_and_citation")
            continue
        cites = [(c["law"], c["art"]) for c in CITE.finditer(match["cite"])]
        if not cites or cites[0] not in current:
            skip("cited_article_not_in_current_corpus")
            continue
        others = [pair for pair in dict.fromkeys(cites[1:]) if pair in current and pair != cites[0]]
        cases.append({"id": f"int-{row['article_no']}", "tier": "interpretation", "query": match["issue"],
                      "required": [article(*cites[0])], "acceptable": [article(*a) for a in others],
                      "explicit_reference": bool(EXPLICIT.search(match["issue"])),
                      "source": f"법제처 법령해석 {row['article_no']}, first cited article"})

    seen_queries = set()
    for case in json.loads(LEGACY.read_text(encoding="utf-8"))["cases"]:
        required = [(j["evidence"]["law"], j["evidence"]["reference"]) for j in case["judgments"]
                    if j["label"] == "required" and j["evidence"].get("kind", "law") == "law"]
        required = [pair for pair in required if pair in current]
        if not required or case["input"]["query"] in seen_queries:
            skip("legacy_without_current_required_article")
            continue
        seen_queries.add(case["input"]["query"])
        hard = [(j["evidence"]["law"], j["evidence"]["reference"]) for j in case["judgments"]
                if j["label"] == "hard_negative"]
        cases.append({"id": f"leg-{case['id']}", "tier": "legacy", "query": case["input"]["query"],
                      "required": [article(*required[0])], "acceptable": [article(*a) for a in required[1:]],
                      "hard_negatives": [article(*a) for a in hard],
                      "source": "evaluation/datasets/retrieval.json (draft labels)"})

    tiers = {}
    for case in cases:
        tiers[case["tier"]] = tiers.get(case["tier"], 0) + 1
    dataset = {
        "name": "embedding-retrieval",
        "version": "1.0.0",
        "description": "Statute-article retrieval set for comparing embedding models and the hybrid search. "
                       "Labels are not reviewed by a tax expert; see evaluation/build_embedding_set.py.",
        "tiers": tiers,
        "skipped": skipped,
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "tiers": tiers, "skipped": skipped}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(build())
