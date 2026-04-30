"""
test_api_auth.py — 인증 엔드포인트 테스트

Pydantic 유효성 검사(422)와 서비스 레이어 응답을 검증한다.
실제 DB 호출은 mock으로 대체한다.
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException


# ── 유효성 검사 (422) ─────────────────────────────────────────────

def test_signup_missing_email_returns_422(client):
    resp = client.post("/api/auth/signup", json={"password": "pass1234"})
    assert resp.status_code == 422


def test_signup_missing_password_returns_422(client):
    resp = client.post("/api/auth/signup", json={"email": "test@example.com"})
    assert resp.status_code == 422


def test_signup_invalid_email_returns_422(client):
    resp = client.post("/api/auth/signup", json={"email": "notanemail", "password": "pass1234"})
    assert resp.status_code == 422


def test_login_missing_fields_returns_422(client):
    resp = client.post("/api/auth/login", json={})
    assert resp.status_code == 422


# ── 정상 흐름 (서비스 mock) ──────────────────────────────────────

def test_signup_success_returns_201(client):
    with patch(
        "app.services.auth_service.signup",
        AsyncMock(return_value={"message": "회원가입 완료", "user_id": "uuid"}),
    ):
        resp = client.post(
            "/api/auth/signup",
            json={"email": "new@example.com", "password": "pass1234"},
        )
    assert resp.status_code == 201


def test_signup_duplicate_email_returns_409(client):
    with patch(
        "app.services.auth_service.signup",
        AsyncMock(side_effect=HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")),
    ):
        resp = client.post(
            "/api/auth/signup",
            json={"email": "dup@example.com", "password": "pass1234"},
        )
    assert resp.status_code == 409


def test_login_success_sets_cookie(client):
    import uuid
    from app.utils.jwt import create_access_token

    token = create_access_token(str(uuid.uuid4()), "user@example.com")
    with patch(
        "app.services.auth_service.login",
        AsyncMock(return_value={
            "access_token": token,
            "token_type": "bearer",
            "user": {"id": "some-uuid", "email": "user@example.com"},
        }),
    ):
        resp = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "pass1234"},
        )
    assert resp.status_code == 200
    assert "access_token" in resp.cookies


def test_login_wrong_password_returns_401(client):
    with patch(
        "app.services.auth_service.login",
        AsyncMock(side_effect=HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")),
    ):
        resp = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "wrong"},
        )
    assert resp.status_code == 401


def test_logout_clears_cookie(client):
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
