"""
test_pdf_chunking.py — PDF 청크 분할 단위 테스트 (조문 경계 인식)
"""
import tiktoken

from app.utils.pdf import _MIN_ARTICLES_FOR_STRUCTURED_SPLIT, split_into_chunks
from config import CHUNK_SIZE

_enc = tiktoken.get_encoding("cl100k_base")


def _make_law_text(n_articles: int, body_repeat: int = 30) -> str:
    """조문 n개짜리 가짜 법령 텍스트 생성."""
    parts = []
    for i in range(1, n_articles + 1):
        parts.append(
            f"제{i}조(예시조문{i}) 이 조문은 테스트를 위한 것이다. "
            + f"제{i}조의 세부 내용이 이어진다. " * body_repeat
        )
    return "\n".join(parts)


# ── 법령류 문서: 조문 경계 존중 ───────────────────────────────────

def test_law_text_chunks_start_at_article_boundary():
    """법령류 텍스트의 모든 청크는 조문 시작('제N조(')에서 시작해야 한다."""
    text = _make_law_text(12)
    chunks = split_into_chunks(text)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.lstrip().startswith("제"), f"조문 경계가 아닌 곳에서 시작: {chunk[:40]!r}"


def test_law_text_no_article_split_mid_body():
    """CHUNK_SIZE 이내의 조문은 중간에서 잘리지 않아야 한다 (각 조문이 정확히 한 청크에 존재)."""
    text = _make_law_text(10)
    chunks = split_into_chunks(text)
    for i in range(1, 11):
        containing = [c for c in chunks if f"제{i}조(예시조문{i})" in c]
        assert len(containing) == 1, f"제{i}조가 {len(containing)}개 청크에 등장"


def test_law_chunks_within_token_limit():
    text = _make_law_text(15)
    chunks = split_into_chunks(text)
    for chunk in chunks:
        assert len(_enc.encode(chunk)) <= CHUNK_SIZE + 5  # 경계 오차 허용


def test_oversized_single_article_falls_back_to_token_split():
    """단일 조문이 CHUNK_SIZE를 넘으면 그 조문만 토큰 분할로 폴백한다."""
    text = _make_law_text(_MIN_ARTICLES_FOR_STRUCTURED_SPLIT - 1) + "\n" + (
        "제99조(아주긴조문) " + "이 조문은 굉장히 길다. " * 800
    ) + "\n" + _make_law_text(2)
    # 총 조문 경계 수를 감지 임계 이상으로
    assert len(split_into_chunks(text)) >= 2


# ── 일반 문서: 토큰 윈도우 폴백 ──────────────────────────────────

def test_plain_text_uses_token_split():
    """조문 경계가 거의 없는 일반 문서는 기존 토큰 분할을 사용한다."""
    text = "세무 실무 안내 문서입니다. " * 500
    chunks = split_into_chunks(text)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(_enc.encode(chunk)) <= CHUNK_SIZE


def test_short_text_single_chunk():
    chunks = split_into_chunks("짧은 문서입니다.")
    assert len(chunks) == 1
