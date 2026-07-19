"""
services/document/pdf_processor.py — PDF 텍스트 추출 및 청크 분할

법령류 문서(조문 구조가 있는 텍스트)는 "제N조(" 경계를 우선 존중해 분할하고,
일반 문서는 토큰 슬라이딩 윈도우로 분할한다. 토큰 윈도우가 조문 중간을
자르면 잘린 반쪽 청크의 임베딩 품질이 떨어지기 때문.
"""
import io
import re

import PyPDF2
import tiktoken

from config import CHUNK_OVERLAP, CHUNK_SIZE

# 조문 시작 패턴: "제39조(", "제59조의4(" — 조문 제목 괄호까지 있어야 본문 인용과 구분됨
_ARTICLE_BOUNDARY_RE = re.compile(r"(?=제\d+(?:조|조의\d+)\()")
# 이 개수 이상 조문 경계가 감지되면 법령류 문서로 판단
_MIN_ARTICLES_FOR_STRUCTURED_SPLIT = 5


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """PDF 바이트 → 전체 텍스트 추출."""
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    return "\n".join(
        page.extract_text().strip()
        for page in reader.pages
        if page.extract_text()
    )


def _split_tokens(text: str, enc) -> list[str]:
    """토큰 슬라이딩 윈도우 분할 (CHUNK_SIZE / CHUNK_OVERLAP)."""
    tokens = enc.encode(text)
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + CHUNK_SIZE, len(tokens))
        chunks.append(enc.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _split_by_articles(text: str, enc) -> list[str]:
    """조문 경계("제N조(") 기준 분할.

    연속된 조문들을 CHUNK_SIZE 이내로 묶고, 단일 조문이 CHUNK_SIZE를
    넘는 경우에만 해당 조문을 토큰 분할로 폴백한다 — 조문 중간 절단 최소화.
    """
    segments = [s for s in _ARTICLE_BOUNDARY_RE.split(text) if s.strip()]

    chunks: list[str] = []
    buffer = ""
    buffer_tokens = 0

    for segment in segments:
        seg_tokens = len(enc.encode(segment))

        if seg_tokens > CHUNK_SIZE:
            # 단일 조문이 청크 한도 초과 — 쌓인 버퍼를 먼저 내보내고 조문만 토큰 분할
            if buffer:
                chunks.append(buffer)
                buffer, buffer_tokens = "", 0
            chunks.extend(_split_tokens(segment, enc))
            continue

        if buffer_tokens + seg_tokens > CHUNK_SIZE and buffer:
            chunks.append(buffer)
            buffer, buffer_tokens = "", 0

        buffer += segment
        buffer_tokens += seg_tokens

    if buffer:
        chunks.append(buffer)
    return chunks


def split_into_chunks(text: str) -> list[str]:
    """텍스트를 임베딩용 청크로 분할한다.

    조문 경계("제N조(")가 충분히 감지되면 법령류 문서로 판단해 조문 단위로
    묶어 분할하고, 아니면 토큰 슬라이딩 윈도우(CHUNK_SIZE/CHUNK_OVERLAP)로 분할한다.
    """
    enc = tiktoken.get_encoding("cl100k_base")

    article_count = len(_ARTICLE_BOUNDARY_RE.findall(text))
    if article_count >= _MIN_ARTICLES_FOR_STRUCTURED_SPLIT:
        return _split_by_articles(text, enc)

    return _split_tokens(text, enc)
