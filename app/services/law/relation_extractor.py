"""Conservative explicit named citations; never infer delegation or aliases."""
import re

from app.services.law.reference_parser import InvalidLawReference, SUBITEM_LABELS, parse_law_reference

# Deliberately require quoted full law names. Bare numbers, '법', '같은 법',
# ranges and omitted-law lists are not resolved by guessing the source law.
_CITATION = re.compile(
    r'[「『](?P<law>[^」』\n]+)[」』]\s*'
    r'(?P<ref>제\s*\d+\s*조(?:\s*의\s*\d+)?'
    r'(?:\s*제?\s*\d+\s*항)?'
    r'(?:\s*제?\s*\d+\s*호(?:\s*의\s*\d+)?)?'
    rf'(?:\s*[{SUBITEM_LABELS}]\s*목)?)'
)


def extract_relations(text: str) -> list[dict]:
    results = []
    for match in _CITATION.finditer(text):
        if re.search(r'(?:구|종전의)\s*$', text[:match.start()]):
            continue
        # Do not silently turn the start of a range into a resolved citation.
        if re.match(r'\s*(?:부터|내지|까지|~|∼)', text[match.end():]):
            continue
        try:
            reference = parse_law_reference(match['ref'])
        except InvalidLawReference:
            continue
        results.append({
            'law_name': match['law'].strip(),
            'article_no': reference.article_no,
            'reference': reference.canonical,
            'evidence': match.group(),
        })
    return results
