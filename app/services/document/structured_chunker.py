"""Structure-preserving chunks for user documents; no LLM inference of document facts."""
from dataclasses import dataclass, replace
import re

import tiktoken

from app.services.document.extractors import DocumentBlock, ExtractedDocument
from config import CHUNK_SIZE


_ARTICLE = re.compile(r'(?m)^\s*(제\d+조(?:의\d+)?)\s*\(')
_CLAUSE = re.compile(r'(?m)^\s*([①-㉟]|제\d+항)\s*')
_ITEM = re.compile(r'(?m)^\s*(제\d+호(?:의\d+)?|\d+\.)\s*')
_LEGAL_UNIT = re.compile(r'(?m)^\s*(?:[①-㉟]|제\d+항|제\d+호(?:의\d+)?|\d+\.)\s*')
_SENTENCE = re.compile(r'(?<=[.!?。])\s+|\n+')


@dataclass(frozen=True)
class StructuredChunk:
    text: str
    metadata: dict


def _parts(text: str, enc, budget: int) -> list[str]:
    """Only oversize units are split; prefer sentence breaks to arbitrary tokens."""
    sentences = [part.strip() for part in _SENTENCE.split(text) if part.strip()]
    output: list[str] = []
    buffer = ''
    for sentence in sentences:
        candidate = f'{buffer}\n{sentence}'.strip() if buffer else sentence
        if len(enc.encode(candidate)) <= budget:
            buffer = candidate
            continue
        if buffer:
            output.append(buffer)
            buffer = ''
        tokens = enc.encode(sentence)
        if len(tokens) > budget:
            output.extend(enc.decode(tokens[i:i + budget]) for i in range(0, len(tokens), budget))
        else:
            buffer = sentence
    if buffer:
        output.append(buffer)
    return output


def _legal_blocks(blocks: tuple[DocumentBlock, ...]) -> tuple[DocumentBlock, ...]:
    """Split only explicit article headings; never guess articles from inline citations."""
    output: list[DocumentBlock] = []
    for block in blocks:
        if block.kind in {'table_row', 'table_header'}:
            output.append(block)
            continue
        matches = list(_ARTICLE.finditer(block.text))
        if not matches:
            output.append(block)
            continue
        if matches[0].start():
            prefix = block.text[:matches[0].start()].strip()
            if prefix:
                output.append(DocumentBlock(prefix, block.kind, block.page, block.slide,
                                            block.section, block.heading, block.table, block.row, block.ocr))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(block.text)
            value = block.text[match.start():end].strip()
            submatches = [unit for unit in _LEGAL_UNIT.finditer(value) if unit.start() > 0]
            if not submatches:
                output.append(DocumentBlock(value, 'article', block.page, block.slide,
                                            block.section, block.heading, block.table, block.row, block.ocr))
                continue
            boundaries = [0] + [unit.start() for unit in submatches] + [len(value)]
            for position in range(len(boundaries) - 1):
                part = value[boundaries[position]:boundaries[position + 1]].strip()
                if not part:
                    continue
                kind = 'article' if position == 0 else (
                    'clause' if _CLAUSE.match(part) else 'item')
                output.append(DocumentBlock(part, kind, block.page, block.slide,
                                            block.section, block.heading, block.table, block.row, block.ocr))
    return tuple(output)


def chunk_document(document: ExtractedDocument) -> list[StructuredChunk]:
    """Keep source boundaries and exact provenance while limiting embedding input size."""
    from app.services.document.pdf_processor import split_into_chunks

    if not document.blocks:
        return [StructuredChunk(text, {'kind': 'text'}) for text in split_into_chunks(document.text)]

    enc = tiktoken.get_encoding('cl100k_base')
    blocks = _legal_blocks(document.blocks)
    chunks: list[StructuredChunk] = []
    active_article = ''
    active_paragraph = ''
    active_item = ''
    table_headers: dict[tuple[int | None, int | None, int | None, int], str] = {}
    for block in blocks:
        if block.kind == 'paragraph' and active_article:
            if _CLAUSE.match(block.text):
                block = replace(block, kind='clause')
            elif _ITEM.match(block.text):
                block = replace(block, kind='item')
        if block.kind == 'article':
            match = _ARTICLE.match(block.text)
            active_article = match.group(1) if match else ''
            active_paragraph = ''
            active_item = ''
        elif block.kind == 'clause':
            match = _CLAUSE.match(block.text)
            active_paragraph = match.group(1) if match else ''
            active_item = ''
        elif block.kind == 'item':
            match = _ITEM.match(block.text)
            active_item = match.group(1) if match else ''
        elif block.kind == 'heading':
            active_article = ''
            active_paragraph = ''
            active_item = ''

        metadata = {
            'kind': block.kind,
            'page': block.page,
            'slide': block.slide,
            'section': block.section,
            'heading': block.heading or None,
            'table': block.table,
            'row': block.row,
            'ocr': block.ocr,
            'article_no': active_article or None,
            'paragraph_ref': active_paragraph or None,
            'item_ref': active_item or None,
        }
        if block.kind in {'table_row', 'table_header'} and block.table:
            table_key = (block.page, block.slide, block.section, block.table)
            if block.kind == 'table_header':
                table_headers[table_key] = block.text
            elif table_key in table_headers:
                metadata['table_header'] = table_headers[table_key]

        labels = []
        if block.page:
            labels.append(f'페이지 {block.page}')
        if block.slide:
            labels.append(f'슬라이드 {block.slide}')
        if block.section:
            labels.append(f'구역 {block.section}')
        if block.heading and block.heading != block.text:
            labels.append(block.heading)
        if metadata.get('table_header'):
            labels.append(f"표 머리글: {metadata['table_header']}")
        if active_article:
            labels.append(active_article)
        if active_paragraph and block.kind != 'clause':
            labels.append(active_paragraph)
        if active_item and block.kind != 'item':
            labels.append(active_item)
        prefix = ' | '.join(labels)
        prefix = f'[{prefix}]\n' if prefix else ''
        budget = max(1, CHUNK_SIZE - len(enc.encode(prefix)))
        for part in _parts(block.text, enc, budget):
            part_metadata = dict(metadata)
            if active_article:
                clause = _CLAUSE.search(part)
                item = _ITEM.search(part)
                if clause:
                    part_metadata['paragraph_ref'] = clause.group(1)
                if item:
                    part_metadata['item_ref'] = item.group(1)
            chunks.append(StructuredChunk(prefix + part, part_metadata))
    return chunks
