"""Approval Schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ApprovalActionCreate(BaseModel):
    """Schema for an approval action (approve/reject/etc.)."""
    action: str = Field(..., description="approved, rejected, sent_back, delegated")
    comments: Optional[str] = Field(None, max_length=2000)
    delegate_to_email: Optional[str] = None  # For delegation


class ApprovalStepResponse(BaseModel):
    """Schema for approval step response."""
    id: int
    step_order: int
    step_name: str
    approval_type: str
    approver_email: str
    approver_name: Optional[str] = None
    approver_role: Optional[str] = None
    status: str
    is_active: bool
    delegated_to_email: Optional[str] = None
    delegated_to_name: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApprovalActionResponse(BaseModel):
    """Schema for approval action response."""
    id: int
    action: str
    comments: Optional[str] = None
    approver_name: Optional[str] = None
    approver_email: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ApprovalHistoryResponse(BaseModel):
    """Full approval history for a request."""
    request_id: str
    steps: List[ApprovalStepResponse]
    actions: List[ApprovalActionResponse]
