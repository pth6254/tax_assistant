"""Regex extraction of explicit references and protected user values.

Extraction never establishes legal applicability or calculation intent. Only
literal reference-only requests use the exact-source search route.
"""
from dataclasses import dataclass, replace
import re

from app.services.law.reference_parser import parse_law_reference, LawReference, SUBITEM_LABELS

BASE_LAWS = ('소득세법', '법인세법', '부가가치세법', '상속세 및 증여세법', '국세기본법',
             '조세특례제한법', '지방세법', '지방세기본법', '지방세특례제한법', '관세법',
             '국세징수법', '조세범처벌법', '종합부동산세법', '인지세법', '교육세법',
             '개별소비세법', '증권거래세법', '농어촌특별세법', '주세법',
             '교통에너지환경세법', '국제조세조정에관한법률')
LAW_ALIASES = {'상증세법': '상속세 및 증여세법', '부가세법': '부가가치세법',
               '조특법': '조세특례제한법', '국기법': '국세기본법'}
_NAME = re.compile(r'(?<![가-힣A-Za-z0-9])(?:[「“"]\s*)?(?P<law>(?:' + '|'.join(re.escape(name).replace(r'\ ', r'\s*')
                       for name in sorted((*BASE_LAWS, *LAW_ALIASES), key=len, reverse=True))
                   + r')(?:\s*시행(?:규칙|령))?)(?:\s*[」”"])?\s*$')
# Unknown explicit names stay literal: a suffix such as "소득세법" inside a
# different name must never promote that request to a known law.
_OTHER_NAME = re.compile(r'(?<![가-힣A-Za-z0-9])(?:[「“"]\s*)?'
                         r'(?P<law>[가-힣A-Za-z0-9]+법(?:률)?(?:\s*시행(?:규칙|령))?)'
                         r'(?:\s*[」”"])?\s*$')
_ARTICLE = re.compile(r'(?:제\s*)?\d+\s*조(?:\s*의\s*\d+)?'
                      r'(?:\s*(?:(?:제\s*)?\d+\s*항|[①-⑳㉑-㉟]))?'
                      r'(?:\s*(?:제\s*)?\d+\s*호(?:\s*의\s*\d+)?)?'
                      rf'(?:\s*[{SUBITEM_LABELS}]\s*목)?')
_VALUES = re.compile(r'\d[\d,.]*(?:\s*[억만천백십]\s*)*(?:원|만원|억원|%|퍼센트|년|월|일)?')
_DATE = re.compile(r'\b(?:19|20)\d{2}\s*(?:년|[-./]\s*\d{1,2}(?:\s*[-./]\s*\d{1,2})?)')
_LOOKUP_WORDS = re.compile(r'원문|전문|조문|내용|뭐라고|어떻게|되어|있는지|있는가|있는|있나요|'
                          r'알려주세요|알려줘|보여주세요|보여줘|설명해주세요|설명해줘|궁금해요|궁금해|'
                          r'주세요|부탁해요|확인해줘|각각|그리고|및|와|과|을|를|이|가|에|는|은|요')


def canonical_law(name):
    compact = name.replace(' ', '')
    for alias, canonical in LAW_ALIASES.items():
        for suffix in ('', ' 시행령', ' 시행규칙'):
            if compact == (alias + suffix).replace(' ', ''):
                return canonical + suffix
    for base in BASE_LAWS:
        for suffix in ('', ' 시행령', ' 시행규칙'):
            if compact == (base + suffix).replace(' ', ''):
                return base + suffix
    return name


@dataclass(frozen=True)
class SearchConstraints:
    references: tuple[LawReference, ...]
    protected_spans: tuple[tuple[int, int], ...]
    date_count: int
    amount_count: int
    lookup_only: bool


def extract_constraints(query):
    references, spans = [], []
    for match in _ARTICLE.finditer(query):
        prefix = query[:match.start()]
        name = _NAME.search(prefix) or _OTHER_NAME.search(prefix)
        ref = replace(parse_law_reference(match.group()),
                      law_name=canonical_law(name.group('law').strip()) if name else None)
        references.append(ref)
        spans.append((name.start() if name else match.start(), match.end()))
    residue = query
    for start, end in reversed(spans):
        residue = residue[:start] + ' ' + residue[end:]
    asked_for_text = bool(re.search(r'원문|전문|내용|뭐라고|조문|보여', residue))
    residue = _LOOKUP_WORDS.sub('', residue)
    residue = re.sub(r'[\s.,!?，。！？·:;()\[\]→~"“”]+', '', residue)
    lookup_only = bool(references and all(r.law_name for r in references)
                       and asked_for_text and not residue)
    values = [(m.start(), m.end()) for m in _VALUES.finditer(query)]
    return SearchConstraints(tuple(references), tuple(spans + values),
                             len(_DATE.findall(query)), len(values), lookup_only)
