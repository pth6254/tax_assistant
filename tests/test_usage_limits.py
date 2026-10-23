"""Daily question limits and the sign-up invite code for a shared link (no database)."""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.security import client_address
from app.services import auth_service, usage_limits

USER = uuid.uuid4()


class UsageConn:
    def __init__(self, mine=0, everyone=0):
        self.mine, self.everyone, self.inserted, self.locked = mine, everyone, [], False

    def transaction(self):
        class Transaction:
            async def __aenter__(self):
                return None

            async def __aexit__(self, *exc):
                return False
        return Transaction()

    async def execute(self, sql, *args):
        if "pg_advisory_xact_lock" in sql:
            self.locked = True
        elif sql.startswith("INSERT INTO chat_usage"):
            self.inserted.append(args)

    async def fetchval(self, sql, *args):
        return self.mine if "user_id" in sql else self.everyone


@pytest.mark.asyncio
async def test_a_question_is_recorded_until_the_users_daily_limit(monkeypatch):
    monkeypatch.setattr(usage_limits.config, "CHAT_DAILY_LIMIT_PER_USER", 20)
    monkeypatch.setattr(usage_limits.config, "CHAT_DAILY_LIMIT_TOTAL", 0)
    conn = UsageConn(mine=19)
    await usage_limits.reserve_question(conn, USER, "question")
    assert conn.locked and conn.inserted == [(USER, "question")]
    with pytest.raises(HTTPException) as error:
        await usage_limits.reserve_question(UsageConn(mine=20), USER, "regeneration")
    assert error.value.status_code == 429 and error.value.detail["code"] == "daily_question_limit"


@pytest.mark.asyncio
async def test_the_whole_service_has_its_own_daily_cap(monkeypatch):
    monkeypatch.setattr(usage_limits.config, "CHAT_DAILY_LIMIT_PER_USER", 20)
    monkeypatch.setattr(usage_limits.config, "CHAT_DAILY_LIMIT_TOTAL", 100)
    conn = UsageConn(mine=0, everyone=100)
    with pytest.raises(HTTPException) as error:
        await usage_limits.reserve_question(conn, USER, "question")
    assert error.value.detail["code"] == "daily_service_limit" and conn.inserted == []


def test_the_day_is_the_korean_calendar_day():
    from datetime import timezone
    late_utc = datetime(2026, 10, 23, 16, 30, tzinfo=timezone.utc)   # 2026-10-24 01:30 KST
    assert usage_limits.day_start(late_utc).isoformat() == "2026-10-24T00:00:00+09:00"


@pytest.mark.asyncio
async def test_sign_up_needs_the_invite_code_when_one_is_set(monkeypatch):
    monkeypatch.setattr(auth_service.config, "SIGNUP_INVITE_CODE", "friends-2026")
    with pytest.raises(HTTPException) as error:
        await auth_service.signup("a@example.com", "correct horse", "wrong")
    assert error.value.status_code == 403

    calls = []

    class Conn:
        async def fetchval(self, sql, *args):
            calls.append(sql)
            return None if sql.startswith("SELECT") else USER

    class Acquire:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *exc):
            return False

    async def get_pool():
        return SimpleNamespace(acquire=Acquire)
    monkeypatch.setattr(auth_service, "get_pool", get_pool)
    assert (await auth_service.signup("a@example.com", "correct horse", " friends-2026 "))["user_id"] == str(USER)


def test_the_visitor_address_comes_from_cloudflare_when_tunnelled():
    def request(headers, host="172.18.0.5"):
        return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))
    assert client_address(request({"cf-connecting-ip": "203.0.113.7", "x-real-ip": "172.18.0.1"})) == "203.0.113.7"
    assert client_address(request({"x-real-ip": "192.0.2.4"})) == "192.0.2.4"
    assert client_address(request({})) == "172.18.0.5"
