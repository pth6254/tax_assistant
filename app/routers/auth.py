"""
routers/auth.py — 인증 엔드포인트
POST /api/auth/signup
POST /api/auth/login
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field, Emailstr


from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email:    Emailstr
    password: str = Field(min_length=1, max_length=72)


class LoginRequest(BaseModel):
    email:    Emailstr
    password: str = Field(min_length=1)


@router.post("/signup", status_code=201)
async def signup(body: SignupRequest):
    return await auth_service.signup(body.email, body.password)


@router.post("/login")
async def login(body: LoginRequest):
    return await auth_service.login(body.email, body.password)
