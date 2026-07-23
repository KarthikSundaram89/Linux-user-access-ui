"""Access Request Schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class ServerInput(BaseModel):
    """Schema for server input (hostname or IP)."""
    hostname: Optional[str] = None
    ip_address: Optional[str] = None

    @field_validator("hostname", "ip_address")
    @classmethod
    def at_least_one(cls, v, info):
        return v


class AccessRequestCreate(BaseModel):
    """Schema for creating an access request."""
    access_type: str = Field(..., description="user_access, sudo_access, both, or renew_sudo")
    environment: str = Field(..., description="production, non_production, development, dr, uat")
    purpose: str = Field(..., min_length=10, max_length=1000)
    business_justification: str = Field(..., min_length=10, max_length=2000)
    application_name: Optional[str] = Field(None, max_length=255)
    project_name: Optional[str] = Field(None, max_length=255)
    servers: List[ServerInput] = Field(..., min_length=1)
    is_renewal: bool = False
    original_request_id: Optional[int] = None

    @field_validator("servers")
    @classmethod
    def validate_servers(cls, v):
        """Validate no duplicate servers."""
        seen = set()
        for server in v:
            key = (server.hostname, server.ip_address)
            if key in seen:
                raise ValueError(f"Duplicate server: {server.hostname or server.ip_address}")
            seen.add(key)
        return v

    @field_validator("access_type")
    @classmethod
    def validate_access_type(cls, v):
        valid_types = ["user_access", "sudo_access", "both", "renew_sudo"]
        if v not in valid_types:
            raise ValueError(f"Invalid access type. Must be one of: {valid_types}")
        return v

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        valid_envs = ["production", "non_production", "development", "dr", "uat"]
        if v not in valid_envs:
            raise ValueError(f"Invalid environment. Must be one of: {valid_envs}")
        return v


class AccessRequestUpdate(BaseModel):
    """Schema for updating a request."""
    status: Optional[str] = None
    purpose: Optional[str] = None
    business_justification: Optional[str] = None


class ServerResponse(BaseModel):
    """Schema for server in response."""
    id: int
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    provisioning_status: str
    provisioning_message: Optional[str] = None
    provisioned_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AccessRequestResponse(BaseModel):
    """Schema for access request response."""
    id: int
    request_id: str
    access_type: str
    environment: str
    purpose: str
    business_justification: str
    application_name: Optional[str] = None
    project_name: Optional[str] = None
    status: str
    current_approval_step: int
    sudo_expiry_date: Optional[datetime] = None
    is_renewal: bool
    servers: List[ServerResponse] = []
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    approved_at: Optional[datetime] = None
    provisioned_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AccessRequestListResponse(BaseModel):
    """Schema for list of requests with pagination."""
    items: List[AccessRequestResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
