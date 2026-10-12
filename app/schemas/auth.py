from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field


def _fits_bcrypt(value: str) -> str:
    # bcrypt reads 72 bytes; a longer password would be silently cut (a Korean letter is 3 bytes).
    if len(value.encode("utf-8")) > 72:
        raise ValueError("비밀번호는 72바이트(영문 72자, 한글 24자) 이하여야 합니다.")
    return value


NewPassword = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(_fits_bcrypt)]


class SignupRequest(BaseModel):
    email: EmailStr
    password: NewPassword


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    phone: str
    business_type: str
    created_at: str


class ProfileUpdateRequest(BaseModel):
    name:          str = Field(default='', max_length=50)
    phone:         str = Field(default='', max_length=20)
    business_type: str = Field(default='개인_일반과세')


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: NewPassword


class DeleteAccountRequest(BaseModel):
    password: str
