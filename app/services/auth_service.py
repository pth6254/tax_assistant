"""
services/auth_service.py — 회원가입·로그인·회원관리 비즈니스 로직
DB 접근과 비밀번호 해싱을 담당합니다.
"""
import logging
import time
import uuid as _uuid
from collections import defaultdict, deque

import asyncpg
from fastapi import HTTPException

from app.database import get_pool
from app.core.security import burn_password_check, create_access_token, hash_password, verify_password

# Logs name accounts by id only; email addresses are personal data and stay out of them.
logger = logging.getLogger(__name__)

DUPLICATE_EMAIL = "이미 사용 중인 이메일입니다."


class LoginThrottle:
    """Failed logins per account and per client address within a sliding window.

    In memory and per process: the service runs one uvicorn worker. A restart forgets
    the counts, which only resets the wait; it never lets a wrong password through.
    """

    def __init__(self, per_account=5, per_client=30, window_sec=900, clock=time.monotonic):
        self.limits = {"account": per_account, "client": per_client}
        self.window, self.clock = window_sec, clock
        self.failures = defaultdict(deque)

    def _recent(self, key):
        now, times = self.clock(), self.failures[key]
        while times and now - times[0] >= self.window:
            times.popleft()
        return times

    def check(self, account, client):
        for kind, key in (("account", account), ("client", client)):
            if key and len(self._recent((kind, key))) >= self.limits[kind]:
                raise HTTPException(status_code=429, detail="로그인 시도가 너무 많습니다. 15분 뒤 다시 시도해 주세요.")

    def fail(self, account, client):
        for kind, key in (("account", account), ("client", client)):
            if key:
                self._recent((kind, key)).append(self.clock())

    def succeed(self, account):
        self.failures.pop(("account", account), None)


login_throttle = LoginThrottle()


async def signup(email: str, password: str) -> dict:
    hashed = hash_password(password)
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
        if exists:
            raise HTTPException(status_code=409, detail=DUPLICATE_EMAIL)
        try:
            user_id = await conn.fetchval(
                "INSERT INTO users (email, password) VALUES ($1, $2) RETURNING id",
                email, hashed,
            )
        except asyncpg.UniqueViolationError:
            # Two sign-ups with one email at the same moment: the second is a duplicate, not a crash.
            raise HTTPException(status_code=409, detail=DUPLICATE_EMAIL) from None
    logger.info("[AUTH] 회원가입 완료 (id=%s)", user_id)
    return {"message": "회원가입 완료", "user_id": str(user_id)}


async def login(email: str, password: str, client: str | None = None) -> dict:
    account = email.strip().lower()
    login_throttle.check(account, client)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, password FROM users WHERE email = $1", email
        )
    if row is None:
        burn_password_check(password)
    if row is None or not verify_password(password, row["password"]):
        login_throttle.fail(account, client)
        logger.warning("[AUTH] 로그인 실패")
        raise HTTPException(
            status_code=401,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    login_throttle.succeed(account)
    token = create_access_token(str(row["id"]), row["email"])
    logger.info("[AUTH] 로그인 성공 (id=%s)", row["id"])
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": {"id": str(row["id"]), "email": row["email"]},
    }


async def get_me(user_id: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, phone, business_type, created_at FROM users WHERE id = $1",
            _uuid.UUID(user_id),
        )
    if not row:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return {
        "id":            str(row["id"]),
        "email":         row["email"],
        "name":          row["name"],
        "phone":         row["phone"],
        "business_type": row["business_type"],
        "created_at":    row["created_at"].isoformat(),
    }


async def update_profile(user_id: str, name: str, phone: str, business_type: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET name = $1, phone = $2, business_type = $3 WHERE id = $4",
            name, phone, business_type, _uuid.UUID(user_id),
        )
    logger.info("[AUTH] 프로필 업데이트: %s", user_id)
    return {"message": "프로필이 업데이트되었습니다."}


async def change_password(user_id: str, current_password: str, new_password: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT password FROM users WHERE id = $1", _uuid.UUID(user_id)
        )
    if not row or not verify_password(current_password, row["password"]):
        raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다.")
    hashed = hash_password(new_password)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET password = $1 WHERE id = $2",
            hashed, _uuid.UUID(user_id),
        )
    logger.info("[AUTH] 비밀번호 변경: %s", user_id)
    return {"message": "비밀번호가 변경되었습니다."}


async def delete_account(user_id: str, password: str) -> dict:
    uid = _uuid.UUID(user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT password FROM users WHERE id = $1", uid
        )
    if not row or not verify_password(password, row["password"]):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    # Everything the user owns references users(id) ON DELETE CASCADE (Alembic 0023), so one
    # statement removes it all; the transaction keeps a failure from leaving half an account.
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM users WHERE id = $1", uid)
    logger.info("[AUTH] 계정 삭제: %s", user_id)
    return {"message": "계정이 삭제되었습니다."}
