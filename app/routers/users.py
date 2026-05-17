"""
routers/users.py — 회원 관리 엔드포인트
GET    /api/users/me             내 정보 조회
PATCH  /api/users/me             프로필 수정 (이름, 전화번호)
PATCH  /api/users/me/password    비밀번호 변경
DELETE /api/users/me             회원 탈퇴
"""
from fastapi import APIRouter, Depends, Response

from app.schemas.auth import DeleteAccountRequest, PasswordChangeRequest, ProfileUpdateRequest, UserResponse
from app.services import auth_service
from app.utils.jwt import clear_auth_cookie, verify_token

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(verify_token)):
    return await auth_service.get_me(user["id"])


@router.patch("/me")
async def update_profile(body: ProfileUpdateRequest, user: dict = Depends(verify_token)):
    return await auth_service.update_profile(user["id"], body.name, body.phone)


@router.patch("/me/password")
async def change_password(body: PasswordChangeRequest, user: dict = Depends(verify_token)):
    return await auth_service.change_password(user["id"], body.current_password, body.new_password)


@router.delete("/me")
async def delete_account(
    body: DeleteAccountRequest,
    response: Response,
    user: dict = Depends(verify_token),
):
    result = await auth_service.delete_account(user["id"], body.password)
    clear_auth_cookie(response)
    return result
