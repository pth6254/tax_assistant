"""
routers/auth.py — 인증 엔드포인트
POST /api/auth/signup
POST /api/auth/login
"""
from fastapi import APIRouter, Response
from pydantic import BaseModel, Field, EmailStr

from app.utils.jwt import set_auth_cookie, clear_auth_cookie


from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email:    EmailStr
    password: str = Field(min_length=1, max_length=72)


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str = Field(min_length=1)


@router.post("/signup", status_code=201)
async def signup(body: SignupRequest):
    return await auth_service.signup(body.email, body.password)


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    data = await auth_service.login(body.email, body.password)
    set_auth_cookie(response, data["access_token"])
    return {"user": data["user"]}

@router.post("/logout")
async def logout(response: Response):
    clear_auth_cookie(response)
    return {"message": "로그아웃 완료"}