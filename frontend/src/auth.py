"""
routers/auth.py — 인증 엔드포인트 (httpOnly 쿠키 방식)
POST /api/auth/signup
POST /api/auth/login
POST /api/auth/logout
"""
from fastapi import APIRouter, Response
from pydantic import BaseModel, EmailStr, Field

from app.services import auth_service
from app.utils.jwt import clear_auth_cookie, set_auth_cookie

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email:    EmailStr                   # 이메일 형식 자동 검증
    password: str = Field(min_length=8) # 최소 8자 강제


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str = Field(min_length=1)


@router.post("/signup", status_code=201)
async def signup(body: SignupRequest):
    return await auth_service.signup(body.email, body.password)


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    data = await auth_service.login(body.email, body.password)
    # 토큰을 httpOnly 쿠키에 저장
    set_auth_cookie(response, data["access_token"])
    # 응답 바디에는 토큰 제외 — user 정보만 반환
    return {"user": data["user"]}


@router.post("/logout")
async def logout(response: Response):
    clear_auth_cookie(response)
    return {"message": "로그아웃 완료"}
