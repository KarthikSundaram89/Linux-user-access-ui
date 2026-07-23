"""User Schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserLogin(BaseModel):
    """Emergency admin login schema."""
    username: str
    password: str


class UserCreate(BaseModel):
    """Schema for creating a user (populated from Azure AD)."""
    azure_ad_id: Optional[str] = None
    email: EmailStr
    display_name: str
    department: Optional[str] = None
    job_title: Optional[str] = None
    employee_id: Optional[str] = None
    manager_email: Optional[str] = None
    manager_name: Optional[str] = None


class UserUpdate(BaseModel):
    """Schema for updating user info."""
    display_name: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    manager_email: Optional[str] = None
    manager_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    """Schema for user response."""
    id: int
    email: str
    display_name: str
    department: Optional[str] = None
    job_title: Optional[str] = None
    employee_id: Optional[str] = None
    manager_email: Optional[str] = None
    manager_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True
