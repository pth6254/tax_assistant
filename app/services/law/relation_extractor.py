"""Explicit citations and aliases supported by original-text definitions."""
import re

from app.services.law.reference_parser import InvalidLawReference, SUBITEM_LABELS, parse_law_reference

# Deliberately require quoted full law names. Bare numbers, '법', '같은 법',
# ranges and omitted-law lists are not resolved by guessing the source law.
_REFERENCE = (
    r'(?P<ref>제\s*\d+\s*조(?:\s*의\s*\d+)?'
    r'(?:\s*제?\s*\d+\s*항)?'
    r'(?:\s*제?\s*\d+\s*호(?:\s*의\s*\d+)?)?'
    rf'(?:\s*[{SUBITEM_LABELS}]\s*목)?)'
)
_CITATION = re.compile(r'[「『](?P<law>[^」』\n]+)[」』]\s*' + _REFERENCE)
_ALIAS_CITATION = re.compile(r'(?<![가-힣\w])(?P<law>법|영)\s+' + _REFERENCE)
_DEFINITION = re.compile(
    r'[「『](?P<name>[^」』\n]+)[」』]\s*\(이하\s*["“「](?P<alias>법|영)["”」]\s*이라\s*한다\s*\)')


def alias_definitions(text: str):
    return [(m['alias'], m['name'].strip(), m.end(), m.group()) for m in _DEFINITION.finditer(text)]


def extract_relations(text: str, aliases: dict[str, str] | None = None) -> list[dict]:
    results = []
    matches = [(m, False) for m in _CITATION.finditer(text)]
    if aliases:
        matches += [(m, True) for m in _ALIAS_CITATION.finditer(text)]
    for match, is_alias in sorted(matches, key=lambda pair: pair[0].start()):
        if re.search(r'(?:구|종전의|같은|동일한|해당)\s*$', text[:match.start()]):
            continue
        if is_alias and match['law'] not in aliases:
            continue
        # Do not silently turn the start of a range into a resolved citation.
        if re.match(r'\s*(?:부터|내지|까지|~|∼)', text[match.end():]):
            continue
        try:
            reference = parse_law_reference(match['ref'])
        except InvalidLawReference:
            continue
        results.append({
            'law_name': aliases[match['law']] if is_alias else match['law'].strip(),
            'article_no': reference.article_no,
            'reference': reference.canonical,
            'evidence': match.group(),
            'alias': match['law'] if is_alias else '',
            'offset': match.start(),
        })
    return results
