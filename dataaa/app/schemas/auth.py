from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import RoleEnum


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=10, description="Password must be at least 10 characters long")
    full_name: str | None = None
    
    @field_validator('password')
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if v.isnumeric():
            raise ValueError('Password cannot be entirely numeric')
        return v

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    role: RoleEnum
    full_name: str | None
    is_active: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str
