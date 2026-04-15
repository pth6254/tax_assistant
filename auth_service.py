"""
services/auth_service.py — 회원가입·로그인 비즈니스 로직
DB 접근과 비밀번호 해싱을 담당합니다.
"""
from fastapi import HTTPException
from passlib.context import CryptContext

from app.database import get_pool
from app.utils.jwt import create_access_token

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def signup(email: str, password: str) -> dict:
    """
    1. 이메일 중복 확인
    2. bcrypt 해싱
    3. users 테이블에 저장
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
        if exists:
            raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")

        hashed  = pwd_context.hash(password)
        user_id = await conn.fetchval(
            "INSERT INTO users (email, password) VALUES ($1, $2) RETURNING id",
            email, hashed,
        )
    return {"message": "회원가입 완료", "user_id": str(user_id)}


async def login(email: str, password: str) -> dict:
    """
    1. 이메일 조회
    2. bcrypt 비밀번호 검증
    3. JWT 반환
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, password FROM users WHERE email = $1", email
        )
    if not row or not pwd_context.verify(password, row["password"]):
        raise HTTPException(
            status_code=401,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    token = create_access_token(str(row["id"]), row["email"])
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": {"id": str(row["id"]), "email": row["email"]},
    }
