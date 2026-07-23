"""Common Schemas."""

from typing import Any, Optional, List
from pydantic import BaseModel


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True
    data: Optional[Any] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    database: str
    scheduler: str


class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class DashboardStats(BaseModel):
    """Dashboard statistics."""
    total_users: int = 0
    pending_requests: int = 0
    approved_requests: int = 0
    rejected_requests: int = 0
    provisioning_failures: int = 0
    servers_managed: int = 0
    expiring_sudo: int = 0
    expired_sudo: int = 0


class SearchQuery(BaseModel):
    """Search query parameters."""
    query: str
    field: Optional[str] = None  # user, email, hostname, ip, application, department, request_id, status
    page: int = 1
    page_size: int = 20
