"""
utils/jwt.py — JWT 생성·검증 유틸
라우터의 Depends()에서 verify_token을 주입해 사용합니다.
"""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from config import JWT_ALGORITHM, JWT_EXPIRE_MIN, JWT_SECRET

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MIN)
    return jwt.encode(
        {"sub": user_id, "email": email, "exp": expire},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


async def verify_token(
    request: Request,
    token: str = Depends(oauth2_scheme),
) -> dict:
    """
    Authorization: Bearer <JWT> 검증.
    성공 시 {"id": str, "email": str} 반환.
    """
    if not token:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="인증 토큰이 없습니다.")
        token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub", "")
        email: str   = payload.get("email", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="토큰 페이로드 오류")
        return {"id": user_id, "email": email}
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"유효하지 않은 토큰: {e}")
