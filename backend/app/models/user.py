"""User Model - Stores user information from Azure AD."""

import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship

from ..core.database import Base


class UserRole(str, enum.Enum):
    """User roles in the system."""
    REQUESTER = "requester"
    REPORTING_MANAGER = "reporting_manager"
    CLOUD_MANAGER = "cloud_manager"
    INFOSEC = "infosec"
    ADMINISTRATOR = "administrator"
    SUPER_ADMINISTRATOR = "super_administrator"


class User(Base):
    """User table - populated from Azure AD on login."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    azure_ad_id = Column(String(255), unique=True, nullable=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    department = Column(String(255), nullable=True)
    job_title = Column(String(255), nullable=True)
    employee_id = Column(String(100), nullable=True)
    manager_email = Column(String(255), nullable=True)
    manager_name = Column(String(255), nullable=True)

    # Role & Status
    role = Column(SAEnum(UserRole), default=UserRole.REQUESTER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_emergency_admin = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    access_requests = relationship("AccessRequest", back_populates="requester", foreign_keys="AccessRequest.requester_id")
    approval_actions = relationship("ApprovalAction", back_populates="approver")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"
