"""
test_jwt.py — JWT 토큰 생성·클레임 검증 단위 테스트
"""
import uuid
from datetime import datetime, timezone

import pytest
from jose import jwt

from app.utils.jwt import create_access_token
from config import JWT_ALGORITHM, JWT_SECRET


def _decode(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def test_create_access_token_returns_string():
    token = create_access_token("user-id", "test@example.com")
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_access_token_sub_claim():
    uid = str(uuid.uuid4())
    payload = _decode(create_access_token(uid, "test@example.com"))
    assert payload["sub"] == uid


def test_create_access_token_email_claim():
    payload = _decode(create_access_token("uid", "hello@example.com"))
    assert payload["email"] == "hello@example.com"


def test_create_access_token_has_exp():
    payload = _decode(create_access_token("uid", "test@example.com"))
    assert "exp" in payload
    assert payload["exp"] > datetime.now(timezone.utc).timestamp()


def test_different_users_get_different_tokens():
    token_a = create_access_token("user-a", "a@example.com")
    token_b = create_access_token("user-b", "b@example.com")
    assert token_a != token_b
