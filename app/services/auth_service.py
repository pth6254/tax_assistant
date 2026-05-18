"""
services/auth_service.py — 회원가입·로그인·회원관리 비즈니스 로직
DB 접근과 비밀번호 해싱을 담당합니다.
"""
import logging
import uuid as _uuid

from fastapi import HTTPException
from passlib.context import CryptContext

from app.database import get_pool
from app.utils.jwt import create_access_token

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False)


async def signup(email: str, password: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
        if exists:
            logger.warning("[AUTH] 회원가입 실패 — 이메일 중복: %s", email)
            raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")

        hashed  = pwd_context.hash(password)
        user_id = await conn.fetchval(
            "INSERT INTO users (email, password) VALUES ($1, $2) RETURNING id",
            email, hashed,
        )
    logger.info("[AUTH] 회원가입 완료: %s (id=%s)", email, user_id)
    return {"message": "회원가입 완료", "user_id": str(user_id)}


async def login(email: str, password: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, password FROM users WHERE email = $1", email
        )
    if not row or not pwd_context.verify(password, row["password"]):
        logger.warning("[AUTH] 로그인 실패: %s", email)
        raise HTTPException(
            status_code=401,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    token = create_access_token(str(row["id"]), row["email"])
    logger.info("[AUTH] 로그인 성공: %s", email)
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": {"id": str(row["id"]), "email": row["email"]},
    }


async def get_me(user_id: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, phone, created_at FROM users WHERE id = $1",
            _uuid.UUID(user_id),
        )
    if not row:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return {
        "id":         str(row["id"]),
        "email":      row["email"],
        "name":       row["name"],
        "phone":      row["phone"],
        "created_at": row["created_at"].isoformat(),
    }


async def update_profile(user_id: str, name: str, phone: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET name = $1, phone = $2 WHERE id = $3",
            name, phone, _uuid.UUID(user_id),
        )
    logger.info("[AUTH] 프로필 업데이트: %s", user_id)
    return {"message": "프로필이 업데이트되었습니다."}


async def change_password(user_id: str, current_password: str, new_password: str) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT password FROM users WHERE id = $1", _uuid.UUID(user_id)
        )
    if not row or not pwd_context.verify(current_password, row["password"]):
        raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다.")
    hashed = pwd_context.hash(new_password)
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
    if not row or not pwd_context.verify(password, row["password"]):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM documents    WHERE user_id = $1", uid)
        await conn.execute(
            "DELETE FROM chat_logs WHERE conversation_id IN "
            "(SELECT id FROM conversations WHERE user_id = $1)",
            uid,
        )
        await conn.execute("DELETE FROM conversations WHERE user_id = $1", uid)
        await conn.execute("DELETE FROM users          WHERE id      = $1", uid)
    logger.info("[AUTH] 계정 삭제: %s", user_id)
    return {"message": "계정이 삭제되었습니다."}
