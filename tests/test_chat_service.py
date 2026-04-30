"""
test_chat_service.py — chat_service 단위 테스트
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.chat_service import (
    detect_law_name,
    _build_final_messages,
    _SUMMARY_PROMPT,
)


# ── detect_law_name — 키워드 매핑 ────────────────────────────────

@pytest.mark.asyncio
async def test_detect_law_name_income_tax():
    assert await detect_law_name("소득세 신고 방법이 궁금해요") == "소득세법"


@pytest.mark.asyncio
async def test_detect_law_name_vat():
    assert await detect_law_name("부가세 환급 받으려면 어떻게 하나요") == "부가가치세법"


@pytest.mark.asyncio
async def test_detect_law_name_corporate_tax():
    assert await detect_law_name("법인세 신고 기한은 언제인가요") == "법인세법"


@pytest.mark.asyncio
async def test_detect_law_name_inheritance():
    assert await detect_law_name("상속세 신고 기한이 얼마나 되나요") == "상속세및증여세법"


@pytest.mark.asyncio
async def test_detect_law_name_national_tax_basic():
    assert await detect_law_name("경정청구 기한이 어떻게 되나요") == "국세기본법"


@pytest.mark.asyncio
async def test_detect_law_name_unknown_falls_back_to_all():
    """키워드 미매핑 + Ollama 응답이 후보에 없는 경우 ALL 반환."""
    mock_resp = AsyncMock()
    mock_resp.json.return_value = {"message": {"content": "모르겠음"}}
    mock_resp.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.post       = AsyncMock(return_value=mock_resp)

    with patch("app.services.chat_service.httpx.AsyncClient", return_value=mock_client):
        result = await detect_law_name("오늘 날씨가 정말 좋네요")
    assert result == "ALL"


@pytest.mark.asyncio
async def test_detect_law_name_ollama_error_returns_all():
    """Ollama 호출 실패 시 ALL 반환."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    mock_client.post       = AsyncMock(side_effect=Exception("connection refused"))

    with patch("app.services.chat_service.httpx.AsyncClient", return_value=mock_client):
        result = await detect_law_name("알 수 없는 질문")
    assert result == "ALL"


# ── _build_final_messages ────────────────────────────────────────

def test_build_final_messages_first_is_system():
    msgs = _build_final_messages("질문", "1차답변", "웹결과", [])
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == _SUMMARY_PROMPT


def test_build_final_messages_last_is_user():
    msgs = _build_final_messages("질문", "1차답변", "웹결과", [])
    assert msgs[-1]["role"] == "user"


def test_build_final_messages_user_content_contains_query():
    msgs = _build_final_messages("소득세 신고 방법", "1차답변", "웹결과", [])
    assert "소득세 신고 방법" in msgs[-1]["content"]


def test_build_final_messages_user_content_contains_rag_answer():
    msgs = _build_final_messages("질문", "RAG 1차 답변 내용", "웹결과", [])
    assert "RAG 1차 답변 내용" in msgs[-1]["content"]


def test_build_final_messages_user_content_contains_web_results():
    msgs = _build_final_messages("질문", "1차답변", "Tavily 웹 검색 결과", [])
    assert "Tavily 웹 검색 결과" in msgs[-1]["content"]


def test_build_final_messages_history_inserted():
    history = [
        {"role": "user",      "content": "이전 질문"},
        {"role": "assistant", "content": "이전 답변"},
    ]
    msgs = _build_final_messages("새 질문", "1차답변", "웹결과", history)
    roles = [m["role"] for m in msgs]
    assert "user" in roles
    assert "assistant" in roles
    contents = [m["content"] for m in msgs]
    assert "이전 질문" in contents
    assert "이전 답변" in contents


def test_build_final_messages_empty_history():
    msgs = _build_final_messages("질문", "답변", "웹", [])
    # system + user 두 개만 존재
    assert len(msgs) == 2
