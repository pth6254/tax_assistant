"""
core/security.py — 비밀번호 해시, JWT 생성·검증 및 httpOnly 인증 쿠키 관리
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, Request, Response

from config import COOKIE_SECURE, JWT_ALGORITHM, JWT_EXPIRE_MIN, JWT_SECRET

# bcrypt reads at most 72 bytes. New passwords longer than that are rejected at the API
# (schemas/auth.py); verification truncates the same way the stored hashes were made.
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    data = password.encode("utf-8")
    if len(data) > BCRYPT_MAX_BYTES:
        raise ValueError("password_too_long")
    return bcrypt.hashpw(data, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:BCRYPT_MAX_BYTES], hashed.encode("ascii"))
    except ValueError:
        return False  # A malformed stored hash never authenticates.


# Checked when the account does not exist, so a wrong email costs the same time as a wrong password.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt()).decode("ascii")


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MIN)
    return jwt.encode(
        {"sub": user_id, "email": email, "exp": expire},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=60 * JWT_EXPIRE_MIN,
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key="access_token")


def client_address(request: Request) -> str | None:
    """The visitor's address. Behind Cloudflare Tunnel every request arrives from the tunnel, so the
    address Cloudflare reports is used; the frontend port is bound to localhost, so only the tunnel
    (or this machine) can set that header."""
    for header in ("cf-connecting-ip", "x-real-ip"):
        value = request.headers.get(header, "").strip()
        if value:
            return value
    return request.client.host if request.client else None


async def verify_token(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="인증 토큰이 없습니다.")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="로그인이 만료되었습니다. 다시 로그인해 주세요.")
    except jwt.PyJWTError:
        # The library's message is not shown; it can describe the token's contents.
        raise HTTPException(status_code=401, detail="유효하지 않은 인증 토큰입니다.")
    user_id: str = payload.get("sub", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="토큰 페이로드 오류")
    return {"id": user_id, "email": payload.get("email", "")}
