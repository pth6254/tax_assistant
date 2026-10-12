"""Sign-up, login, password change and account deletion against a fake connection (no database)."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import asyncpg
import bcrypt
import jwt
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core import security
from app.schemas.auth import PasswordChangeRequest, SignupRequest
from app.services import auth_service

USER_ID = uuid.uuid4()


class FakeConn:
    """Answers the statements auth_service sends; records every statement."""

    def __init__(self, user=None, duplicate_on_insert=False):
        self.user, self.duplicate_on_insert = user, duplicate_on_insert
        self.statements, self.in_transaction = [], []

    async def fetchval(self, sql, *args):
        self.statements.append(sql)
        if sql.startswith("SELECT id FROM users"):
            return self.user and self.user["id"]
        if sql.startswith("INSERT INTO users"):
            if self.duplicate_on_insert:
                raise asyncpg.UniqueViolationError("duplicate key value violates unique constraint")
            self.user = {"id": USER_ID, "email": args[0], "password": args[1]}
            return USER_ID

    async def fetchrow(self, sql, *args):
        self.statements.append(sql)
        return self.user

    async def execute(self, sql, *args):
        self.statements.append(sql)
        self.in_transaction.append(self.transaction_open)
        if sql.startswith("UPDATE users SET password"):
            self.user = dict(self.user, password=args[0])

    transaction_open = False

    def transaction(self):
        conn = self

        class Transaction:
            async def __aenter__(self):
                conn.transaction_open = True

            async def __aexit__(self, *exc):
                conn.transaction_open = False
        return Transaction()


@pytest.fixture
def db(monkeypatch):
    holder = SimpleNamespace(conn=FakeConn())

    class Acquire:
        async def __aenter__(self):
            return holder.conn

        async def __aexit__(self, *exc):
            return False

    async def get_pool():
        return SimpleNamespace(acquire=Acquire)
    monkeypatch.setattr(auth_service, "get_pool", get_pool)
    monkeypatch.setattr(auth_service, "login_throttle", auth_service.LoginThrottle())
    return holder


def stored(password="correct horse"):
    return {"id": USER_ID, "email": "a@example.com", "password": security.hash_password(password)}


# ── 비밀번호 해시 ────────────────────────────────────────────────

def test_a_hash_verifies_only_its_password_and_is_not_the_password():
    hashed = security.hash_password("correct horse")
    assert hashed != "correct horse" and hashed.startswith("$2")
    assert security.verify_password("correct horse", hashed)
    assert not security.verify_password("wrong", hashed)
    assert not security.verify_password("correct horse", None)
    assert not security.verify_password("correct horse", "not-a-bcrypt-hash")


def test_hashes_made_by_the_previous_library_still_verify():
    # passlib wrote standard $2b$ hashes of the first 72 bytes; existing accounts keep working.
    long_password = "가" * 30   # 90 bytes
    legacy = bcrypt.hashpw(long_password.encode()[:72], bcrypt.gensalt()).decode()
    assert security.verify_password(long_password, legacy)


def test_a_new_password_over_72_bytes_is_refused_not_cut():
    with pytest.raises(ValueError):
        security.hash_password("가" * 25)   # 75 bytes
    with pytest.raises(ValidationError):
        SignupRequest(email="a@example.com", password="가" * 25)
    with pytest.raises(ValidationError):
        PasswordChangeRequest(current_password="x", new_password="가" * 25)
    assert SignupRequest(email="a@example.com", password="가" * 24).password == "가" * 24
    with pytest.raises(ValidationError):
        SignupRequest(email="a@example.com", password="short")


# ── 회원가입 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sign_up_stores_a_hash_and_refuses_a_taken_email(db):
    result = await auth_service.signup("a@example.com", "correct horse")
    assert result["user_id"] == str(USER_ID)
    assert security.verify_password("correct horse", db.conn.user["password"])
    with pytest.raises(HTTPException) as error:
        await auth_service.signup("a@example.com", "another one")
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_two_sign_ups_at_once_end_in_a_duplicate_not_a_server_error(db):
    db.conn = FakeConn(duplicate_on_insert=True)   # the other request inserted between check and insert
    with pytest.raises(HTTPException) as error:
        await auth_service.signup("a@example.com", "correct horse")
    assert error.value.status_code == 409


# ── 로그인 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_returns_a_token_for_the_right_password_only(db, caplog):
    db.conn = FakeConn(user=stored())
    result = await auth_service.login("a@example.com", "correct horse", "10.0.0.1")
    payload = jwt.decode(result["access_token"], security.JWT_SECRET, algorithms=[security.JWT_ALGORITHM])
    assert payload["sub"] == str(USER_ID)
    with pytest.raises(HTTPException) as error:
        await auth_service.login("a@example.com", "wrong", "10.0.0.1")
    assert error.value.status_code == 401
    assert "a@example.com" not in caplog.text   # logs name the account by id only


@pytest.mark.asyncio
async def test_an_unknown_email_fails_like_a_wrong_password(db, monkeypatch):
    burned = []
    monkeypatch.setattr(auth_service, "burn_password_check", burned.append)
    with pytest.raises(HTTPException) as error:
        await auth_service.login("nobody@example.com", "guess", "10.0.0.1")
    assert error.value.status_code == 401 and burned == ["guess"]


@pytest.mark.asyncio
async def test_repeated_failures_lock_the_account_for_a_while(db, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(auth_service, "login_throttle", auth_service.LoginThrottle(clock=lambda: now[0]))
    db.conn = FakeConn(user=stored())
    for _ in range(5):
        with pytest.raises(HTTPException):
            await auth_service.login("A@example.com", "wrong", "10.0.0.1")
    with pytest.raises(HTTPException) as error:
        await auth_service.login("a@example.com", "correct horse", "10.0.0.2")   # even the right password
    assert error.value.status_code == 429
    now[0] = 901.0   # the window has passed
    assert (await auth_service.login("a@example.com", "correct horse", "10.0.0.1"))["access_token"]


def test_one_client_cannot_try_many_accounts():
    throttle = auth_service.LoginThrottle(per_client=3, clock=lambda: 0.0)
    for n in range(3):
        throttle.fail(f"user{n}@example.com", "10.0.0.9")
    with pytest.raises(HTTPException):
        throttle.check("fresh@example.com", "10.0.0.9")
    throttle.check("fresh@example.com", "10.0.0.8")   # another client is not affected


# ── 토큰 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_expired_or_forged_token_is_refused_without_its_details():
    def request(token):
        return SimpleNamespace(cookies={"access_token": token})
    expired = jwt.encode({"sub": "u", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                         security.JWT_SECRET, algorithm=security.JWT_ALGORITHM)
    forged = jwt.encode({"sub": "u"}, "another-secret", algorithm=security.JWT_ALGORITHM)
    for token, message in ((expired, "만료"), (forged, "유효하지 않은")):
        with pytest.raises(HTTPException) as error:
            await security.verify_token(request(token))
        assert error.value.status_code == 401 and message in error.value.detail
    user = await security.verify_token(request(security.create_access_token("u1", "a@example.com")))
    assert user == {"id": "u1", "email": "a@example.com"}


# ── 비밀번호 변경·탈퇴 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_password_changes_only_with_the_current_one(db):
    db.conn = FakeConn(user=stored())
    with pytest.raises(HTTPException) as error:
        await auth_service.change_password(str(USER_ID), "wrong", "new password 1")
    assert error.value.status_code == 401
    await auth_service.change_password(str(USER_ID), "correct horse", "new password 1")
    assert security.verify_password("new password 1", db.conn.user["password"])


@pytest.mark.asyncio
async def test_deleting_an_account_is_one_statement_in_a_transaction(db):
    db.conn = FakeConn(user=stored())
    with pytest.raises(HTTPException):
        await auth_service.delete_account(str(USER_ID), "wrong")
    assert not any(sql.startswith("DELETE") for sql in db.conn.statements)
    await auth_service.delete_account(str(USER_ID), "correct horse")
    deletes = [sql for sql in db.conn.statements if sql.startswith("DELETE")]
    # Conversations, messages, documents and files follow by ON DELETE CASCADE (Alembic 0023).
    assert deletes == ["DELETE FROM users WHERE id = $1"] and db.conn.in_transaction == [True]
