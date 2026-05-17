from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    phone: str
    created_at: str


class ProfileUpdateRequest(BaseModel):
    name:  str = Field(default='', max_length=50)
    phone: str = Field(default='', max_length=20)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


class DeleteAccountRequest(BaseModel):
    password: str
