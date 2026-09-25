"""Read retained XML trees without rewriting immutable bodies, hashes or vectors."""
import json
import re

from app.services.law.reference_parser import paragraph_label_to_number
from app.services.law.structure_parser import resolve_reference_target


class HistoricalStructureError(ValueError):
    pass


def children(node, tag):
    return [c for c in node.get('children', []) if c.get('tag') == tag]


def text(node, tag):
    return '\n'.join(c.get('text', '').strip() for c in children(node, tag)).strip()


def lead(node):
    kind = node['tag']
    return text(node, '조문내용' if kind == '조문단위' else kind + '내용')


def render(node):
    parts = [lead(node)]
    for child in node.get('children', []):
        if child.get('tag') in {'항', '호', '목'}:
            parts.append(render(child))
    return '\n'.join(p for p in parts if p)


def number(node, kind):
    label = text(node, kind + '번호').strip()
    if kind == '항':
        circled = paragraph_label_to_number(label)
        if circled is not None:
            return circled
        match = re.fullmatch(r'(?:제)?(\d+)(?:항|\.)?', label)
        return int(match[1]) if match else None
    if kind == '호':
        match = re.fullmatch(r'(?:제)?(\d+)(?:호)?(?:의(\d+))?\.?', label)
        return (int(match[1]), int(match[2]) if match[2] else None) if match else None
    return label.removesuffix('.').removesuffix('목')


def units(node, kind):
    result = children(node, kind)
    # Some older XML places unnumbered paragraphs around article-level items.
    if kind == '호':
        for paragraph in children(node, '항'):
            if not text(paragraph, '항번호'):
                result.extend(children(paragraph, kind))
    return result


def article_excerpt(structure, body, reference):
    """Exact subtree plus ancestor introductions (conditions), never sibling items.

    XML numbering is authoritative. Text fallback is only for legacy records with
    no structural units at all; it must not override a missing XML child.
    """
    if isinstance(structure, str):
        structure = json.loads(structure)
    if not structure or not any(children(structure, k) for k in ('항', '호', '목')):
        # Remove only adjacent repeated standalone labels, not labels in prose.
        clean = re.sub(r'(?m)^\s*([①-⑳㉑-㉟]|\d+(?:의\d+)?\.|[가-하]\.)\s*\n(?=\s*\1)', '', body)
        target = resolve_reference_target(clean, reference)
        if target is not None and not target.exists:
            raise HistoricalStructureError('요청한 항·호·목 본문을 확인하지 못했습니다.')
        return target.text if target else clean
    node = structure
    ancestors = []
    for kind, wanted in [('항', reference.paragraph),
                         ('호', (reference.item, reference.item_branch) if reference.item is not None else None),
                         ('목', reference.subitem)]:
        if wanted is None:
            continue
        found = [n for n in units(node, kind) if number(n, kind) == wanted]
        if len(found) != 1:
            raise HistoricalStructureError('요청한 항·호·목을 XML에서 유일하게 확인하지 못했습니다.')
        ancestors.append(lead(node))
        if kind == '호' and found[0] not in children(node, '호'):
            ancestors.extend(lead(p) for p in children(node, '항') if found[0] in children(p, '호'))
        node = found[0]
    result = '\n'.join(p for p in [*ancestors, render(node)] if p)
    if not lead(node):
        raise HistoricalStructureError('요청한 범위의 XML 본문이 비어 있습니다.')
    return result
