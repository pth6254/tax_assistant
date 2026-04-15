"""
utils/jwt.py — JWT 생성·검증 유틸 (httpOnly 쿠키 방식)
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response
from jose import JWTError, jwt

from app.config import JWT_ALGORITHM, JWT_EXPIRE_MIN, JWT_SECRET


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
        secure=False,        # 로컬 개발환경은 False
        samesite="lax",
        max_age=60 * JWT_EXPIRE_MIN,
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key="access_token")


async def verify_token(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="인증 토큰이 없습니다.")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub", "")
        email: str   = payload.get("email", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="토큰 페이로드 오류")
        return {"id": user_id, "email": email}
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"유효하지 않은 토큰: {e}")
