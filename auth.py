"""
routers/auth.py — 인증 엔드포인트
POST /api/auth/signup
POST /api/auth/login
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email:    str
    password: str


class LoginRequest(BaseModel):
    email:    str
    password: str


@router.post("/signup", status_code=201)
async def signup(body: SignupRequest):
    return await auth_service.signup(body.email, body.password)


@router.post("/login")
async def login(body: LoginRequest):
    return await auth_service.login(body.email, body.password)
