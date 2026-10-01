"""One-edit search expansion from a fixed tax vocabulary; original text is kept.

Bounded Damerau-Levenshtein (distance <= 1), including adjacent transposition.
Numbers, references, negation polarity and ambiguous candidates are protected.
"""
import re
import unicodedata

from app.services.search.korean_analyzer import _COMPOUNDS
from app.services.search.query_constraints import BASE_LAWS, extract_constraints

TERMS = frozenset((*_COMPOUNDS, *(n for n in BASE_LAWS if ' ' not in n),
                   '종합소득세', '양도소득세', '지방소득세', '증여재산공제', '금융소득종합과세',
                   '증빙불비', '원천징수', '경정청구', '기한후신고', '연부연납', '의제매입세액',
                   '필요경비', '복리후생비', '업무관련성', '납부기한', '전자세금계산서',
                   '매입세액공제', '매입세액불공제'))
_PARTICLES = re.compile(r'(?:에서는|에서|으로|에게|까지|부터|에는|이나|이라|라는|하고|하여|한다|하는|'
                        r'되는|되어|했다|였다|은|는|이|가|을|를|의|에|과|와|도)$')


def one_edit_apart(left, right):
    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right):
        left, right = right, left
    i = next((i for i, (a, b) in enumerate(zip(left, right)) if a != b), len(left))
    if len(left) != len(right):
        return left[i:] == right[i + 1:]
    if left[i + 1:] == right[i + 1:]:
        return True
    return (i + 1 < len(left) and left[i] == right[i + 1] and left[i + 1] == right[i]
            and left[i + 2:] == right[i + 2:])


def _polarity(word):
    return tuple(marker in word for marker in ('불', '비', '무', '제외', '아니', '않', '못'))


def expand_fuzzy_terms(query, limit=2):
    query = unicodedata.normalize('NFC', query)
    if limit <= 0:
        return query, []
    constraints = extract_constraints(query)
    expansions = []
    for match in re.finditer(r'[가-힣]{4,24}', query):
        if any(match.start() < end and match.end() > start for start, end in constraints.protected_spans):
            continue
        word = match.group()
        # Recognize a correctly spelled compound before stripping its particle.
        if word in TERMS or any(word.startswith(t) and _PARTICLES.fullmatch(word[len(t):]) for t in TERMS):
            continue
        stem = _PARTICLES.sub('', word)
        if len(stem) < 4:
            continue
        candidates = [term for term in sorted(TERMS) if _polarity(stem) == _polarity(term)
                      and one_edit_apart(stem, term)]
        if len(candidates) != 1 or candidates[0] in query or candidates[0] in expansions:
            continue
        expansions.append(candidates[0])
        if len(expansions) >= limit:
            break
    return query + ((' ' + ' '.join(expansions)) if expansions else ''), expansions
