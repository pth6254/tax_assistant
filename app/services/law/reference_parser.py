"""대한민국 법령의 조·항·호·목 참조 파싱과 표준화."""
from dataclasses import dataclass
import re


SUBITEM_LABELS = "가나다라마바사아자차카타파하"
_CIRCLED_TO_NUMBER = {
    **{chr(0x2460 + index): index + 1 for index in range(20)},
    **{chr(0x3251 + index): index + 21 for index in range(15)},
}
_NUMBER_TO_CIRCLED = {number: marker for marker, number in _CIRCLED_TO_NUMBER.items()}
_CIRCLED_CLASS = "①-⑳㉑-㉟"
PARAGRAPH_MARKER_PATTERN = rf"[{_CIRCLED_CLASS}]"
PARAGRAPH_MARKERS = frozenset(_CIRCLED_TO_NUMBER)
_LAW_NAME_PATTERN = r".+?법(?:\s*시행(?:규칙|령))?"
_SEARCH_LAW_NAME_PATTERN = r"[가-힣][가-힣\s·ㆍ]*?법(?:\s*시행(?:규칙|령))?"


class InvalidLawReference(ValueError):
    """입력을 법령 참조 문법으로 해석할 수 없을 때 발생한다."""


@dataclass(frozen=True)
class LawReference:
    law_name: str | None = None
    article: int | None = None
    article_branch: int | None = None
    paragraph: int | None = None
    item: int | None = None
    item_branch: int | None = None
    subitem: str | None = None

    @property
    def article_no(self) -> str | None:
        if self.article is None:
            return None
        return format_article_no(self.article, self.article_branch)

    @property
    def paragraph_no(self) -> str | None:
        return f"제{self.paragraph}항" if self.paragraph is not None else None

    @property
    def paragraph_label(self) -> str | None:
        if self.paragraph is None:
            return None
        return _NUMBER_TO_CIRCLED.get(self.paragraph)

    @property
    def item_no(self) -> str | None:
        if self.item is None:
            return None
        value = f"제{self.item}호"
        if self.item_branch is not None:
            value += f"의{self.item_branch}"
        return value

    @property
    def subitem_no(self) -> str | None:
        return f"{self.subitem}목" if self.subitem else None

    @property
    def canonical(self) -> str:
        return " ".join(filter(None, (
            self.law_name,
            self.article_no,
            self.paragraph_no,
            self.item_no,
            self.subitem_no,
        )))


_REFERENCE_PATTERN = re.compile(
    rf"""
    ^\s*
    (?:(?P<law_name>{_LAW_NAME_PATTERN})\s*)?
    (?:제\s*)?(?P<article>\d+)\s*조
    (?:\s*의\s*(?P<article_branch>\d+))?
    (?:\s*(?:(?:제\s*)?(?P<paragraph>\d+)\s*항|(?P<circled>[{_CIRCLED_CLASS}])))?
    (?:\s*(?:제\s*)?(?P<item>\d+)\s*호(?:\s*의\s*(?P<item_branch>\d+))?)?
    (?:\s*(?P<subitem>[{SUBITEM_LABELS}])\s*목)?
    \s*$
    """,
    re.VERBOSE,
)

_REFERENCE_SEARCH_PATTERN = re.compile(
    rf"""
    (?:(?P<law_name>{_SEARCH_LAW_NAME_PATTERN})\s*)?
    (?:제\s*)?(?P<article>\d+)\s*조
    (?:\s*의\s*(?P<article_branch>\d+))?
    (?:\s*(?:(?:제\s*)?(?P<paragraph>\d+)\s*항|(?P<circled>[{_CIRCLED_CLASS}])))?
    (?:\s*(?:제\s*)?(?P<item>\d+)\s*호(?:\s*의\s*(?P<item_branch>\d+))?)?
    (?:\s*(?P<subitem>[{SUBITEM_LABELS}])\s*목)?
    """,
    re.VERBOSE,
)

_ARTICLE_SHORTHAND_PATTERN = re.compile(
    r"^(?:제)?(?P<article>\d+)(?:조)?(?:의(?P<branch>\d+))?$"
)


def format_article_no(
    article: int | str,
    branch: int | str | None = None,
) -> str:
    """조 번호와 가지번호를 DB 표준형인 ``제N조의N``으로 조립한다."""
    value = f"제{int(article)}조"
    if branch not in (None, ""):
        value += f"의{int(branch)}"
    return value


def _reference_from_groups(groups: dict[str, str | None]) -> LawReference:
    paragraph = groups.get("paragraph")
    circled = groups.get("circled")
    return LawReference(
        law_name=groups.get("law_name").strip() if groups.get("law_name") else None,
        article=int(groups["article"]) if groups.get("article") else None,
        article_branch=int(groups["article_branch"]) if groups.get("article_branch") else None,
        paragraph=int(paragraph) if paragraph else _CIRCLED_TO_NUMBER.get(circled or ""),
        item=int(groups["item"]) if groups.get("item") else None,
        item_branch=int(groups["item_branch"]) if groups.get("item_branch") else None,
        subitem=groups.get("subitem"),
    )


def parse_law_reference(value: str) -> LawReference:
    """완전한 참조 문자열을 파싱한다. 임의의 설명 문장은 허용하지 않는다."""
    if not value or not value.strip():
        raise InvalidLawReference("법령 참조가 비어 있습니다.")
    normalized = re.sub(r"\s+", " ", value.strip())
    match = _REFERENCE_PATTERN.fullmatch(normalized)
    if not match:
        raise InvalidLawReference(f"유효하지 않은 법령 참조 형식입니다: {value}")
    return _reference_from_groups(match.groupdict())


def extract_law_reference(value: str) -> LawReference | None:
    """질문·답변 문장 안의 첫 번째 조·항·호·목 참조를 추출한다."""
    if not value:
        return None
    match = _REFERENCE_SEARCH_PATTERN.search(value)
    return _reference_from_groups(match.groupdict()) if match else None


def normalize_article_no(value: str) -> str:
    """조문 입력을 DB 표준형으로 바꾸고 유권해석 안건번호는 보존한다."""
    compact = re.sub(r"\s+", "", value.strip())
    if not compact:
        return compact

    shorthand = _ARTICLE_SHORTHAND_PATTERN.fullmatch(compact)
    if shorthand:
        return format_article_no(
            shorthand.group("article"), shorthand.group("branch")
        )

    try:
        reference = parse_law_reference(value)
    except InvalidLawReference:
        return compact
    return reference.article_no or compact


def paragraph_number_to_label(number: int) -> str | None:
    return _NUMBER_TO_CIRCLED.get(number)


def paragraph_label_to_number(label: str) -> int | None:
    return _CIRCLED_TO_NUMBER.get(label)
