"""Approval Workflow Models."""

import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, Enum as SAEnum, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from ..core.database import Base


class ApprovalStatus(str, enum.Enum):
    """Status of an approval step."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT_BACK = "sent_back"
    DELEGATED = "delegated"
    ESCALATED = "escalated"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"


class ApprovalType(str, enum.Enum):
    """Type of approval step."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class ApprovalStep(Base):
    """Individual approval step in the workflow."""

    __tablename__ = "approval_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey("access_requests.id"), nullable=False)

    # Step Configuration
    step_order = Column(Integer, nullable=False)
    step_name = Column(String(255), nullable=False)
    approval_type = Column(SAEnum(ApprovalType), default=ApprovalType.SEQUENTIAL)
    approver_email = Column(String(255), nullable=False)
    approver_name = Column(String(255), nullable=True)
    approver_role = Column(String(100), nullable=True)

    # Delegation
    delegated_to_email = Column(String(255), nullable=True)
    delegated_to_name = Column(String(255), nullable=True)
    delegated_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    status = Column(SAEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False)
    is_active = Column(Boolean, default=False)

    # Timing
    reminder_sent = Column(Boolean, default=False)
    reminder_sent_at = Column(DateTime(timezone=True), nullable=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    timeout_hours = Column(Integer, default=48)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    request = relationship("AccessRequest", back_populates="approval_steps")
    actions = relationship("ApprovalAction", back_populates="step", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ApprovalStep(id={self.id}, step={self.step_order}, status='{self.status}')>"


class ApprovalAction(Base):
    """Actions taken on an approval step (approve, reject, comment, etc.)."""

    __tablename__ = "approval_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    step_id = Column(Integer, ForeignKey("approval_steps.id"), nullable=False)
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Action Details
    action = Column(SAEnum(ApprovalStatus), nullable=False)
    comments = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    step = relationship("ApprovalStep", back_populates="actions")
    approver = relationship("User", back_populates="approval_actions")

    def __repr__(self):
        return f"<ApprovalAction(id={self.id}, action='{self.action}')>"
