"""
utils/pdf.py — PDF 파싱 및 청크 분할 유틸
"""
import io

import PyPDF2
import tiktoken

from app.config import CHUNK_OVERLAP, CHUNK_SIZE


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """PDF 바이트 → 전체 텍스트 추출."""
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    return "\n".join(
        page.extract_text().strip()
        for page in reader.pages
        if page.extract_text()
    )


def split_into_chunks(text: str) -> list[str]:
    """
    tiktoken cl100k_base 기준으로 텍스트를 CHUNK_SIZE 토큰 단위로 분할.
    CHUNK_OVERLAP 만큼 슬라이딩 윈도우 적용.
    """
    enc    = tiktoken.get_encoding("cl100k_base")
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
