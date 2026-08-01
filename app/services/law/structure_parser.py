"""법령 조문 본문에서 항·호·목 단위를 찾아 참조와 대조한다."""
from dataclasses import dataclass
import re

from app.services.law.reference_parser import (
    LawReference,
    PARAGRAPH_MARKERS,
    PARAGRAPH_MARKER_PATTERN,
    SUBITEM_LABELS,
    paragraph_label_to_number,
)

_PARAGRAPH_RE = re.compile(rf"(?={PARAGRAPH_MARKER_PATTERN})")
_ITEM_RE = re.compile(r"(?m)^\s*(?P<number>\d+)(?:의(?P<branch>\d+))?\.\s*")
_SUBITEM_RE = re.compile(rf"(?m)^\s*(?P<label>[{SUBITEM_LABELS}])\.\s*")


@dataclass(frozen=True)
class ParagraphText:
    number: int
    label: str
    text: str


@dataclass(frozen=True)
class ReferenceTarget:
    exists: bool
    level: str
    paragraph: int | None = None
    item: int | None = None
    item_branch: int | None = None
    subitem: str | None = None
    text: str | None = None
    detail: str | None = None


def split_paragraphs(article_text: str) -> list[ParagraphText]:
    """길이와 개수 제한 없이 원문의 모든 원문자 항을 분리한다."""
    parts = [part.strip() for part in _PARAGRAPH_RE.split(article_text) if part.strip()]
    result: list[ParagraphText] = []
    for part in parts:
        if not part or part[0] not in PARAGRAPH_MARKERS:
            continue
        number = paragraph_label_to_number(part[0])
        if number is not None:
            result.append(ParagraphText(number=number, label=part[0], text=part))
    return result


def _preamble_before_first_paragraph(article_text: str) -> str:
    match = re.search(PARAGRAPH_MARKER_PATTERN, article_text)
    return article_text[:match.start()].strip() if match else article_text.strip()


def _matching_block(
    text: str,
    pattern: re.Pattern[str],
    predicate,
) -> str | None:
    matches = list(pattern.finditer(text))
    for index, match in enumerate(matches):
        if not predicate(match):
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        return text[match.start():end].strip()
    return None


def _find_item(text: str, number: int, branch: int | None) -> str | None:
    return _matching_block(
        text,
        _ITEM_RE,
        lambda match: int(match.group("number")) == number
        and (int(match.group("branch")) if match.group("branch") else None) == branch,
    )


def _find_subitem(text: str, label: str) -> str | None:
    return _matching_block(
        text,
        _SUBITEM_RE,
        lambda match: match.group("label") == label,
    )


def resolve_reference_target(
    article_text: str,
    reference: LawReference,
) -> ReferenceTarget | None:
    """파싱된 참조의 항·호·목이 본문에 존재하는지 확인하고 가장 구체적인 본문을 반환한다."""
    if reference.paragraph is None and reference.item is None and reference.subitem is None:
        return None

    scope = article_text
    if reference.paragraph is not None:
        paragraph = next(
            (unit for unit in split_paragraphs(article_text) if unit.number == reference.paragraph),
            None,
        )
        if paragraph is None:
            return ReferenceTarget(
                exists=False,
                level="paragraph",
                paragraph=reference.paragraph,
                detail=f"제{reference.paragraph}항이 조문 본문에 없습니다.",
            )
        scope = paragraph.text
        if reference.item is None:
            return ReferenceTarget(
                exists=True,
                level="paragraph",
                paragraph=reference.paragraph,
                text=scope,
            )
    elif reference.item is not None:
        # 항이 없는 조에서 호는 첫 항 기호 이전의 조 본문에 속한다.
        scope = _preamble_before_first_paragraph(article_text)

    if reference.item is not None:
        item_text = _find_item(scope, reference.item, reference.item_branch)
        if item_text is None:
            item_no = f"제{reference.item}호"
            if reference.item_branch is not None:
                item_no += f"의{reference.item_branch}"
            return ReferenceTarget(
                exists=False,
                level="item",
                paragraph=reference.paragraph,
                item=reference.item,
                item_branch=reference.item_branch,
                detail=f"{item_no}가 지정된 범위에 없습니다.",
            )
        scope = item_text
        if reference.subitem is None:
            return ReferenceTarget(
                exists=True,
                level="item",
                paragraph=reference.paragraph,
                item=reference.item,
                item_branch=reference.item_branch,
                text=scope,
            )

    if reference.subitem is not None:
        subitem_text = _find_subitem(scope, reference.subitem)
        if subitem_text is None:
            return ReferenceTarget(
                exists=False,
                level="subitem",
                paragraph=reference.paragraph,
                item=reference.item,
                item_branch=reference.item_branch,
                subitem=reference.subitem,
                detail=f"{reference.subitem}목이 지정된 범위에 없습니다.",
            )
        return ReferenceTarget(
            exists=True,
            level="subitem",
            paragraph=reference.paragraph,
            item=reference.item,
            item_branch=reference.item_branch,
            subitem=reference.subitem,
            text=subitem_text,
        )

    return None
