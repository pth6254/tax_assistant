"""
services/auth_service.py — 회원가입·로그인 비즈니스 로직
DB 접근과 비밀번호 해싱을 담당합니다.
"""
import logging

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
