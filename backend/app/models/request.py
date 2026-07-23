"""Access Request Models."""

import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, Enum as SAEnum, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from ..core.database import Base


class AccessType(str, enum.Enum):
    """Types of access that can be requested."""
    USER_ACCESS = "user_access"
    SUDO_ACCESS = "sudo_access"
    BOTH = "both"
    RENEW_SUDO = "renew_sudo"


class RequestStatus(str, enum.Enum):
    """Status of an access request."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROVISIONING = "provisioning"
    PROVISIONED = "provisioned"
    PARTIALLY_PROVISIONED = "partially_provisioned"
    PROVISIONING_FAILED = "provisioning_failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REVOKED = "revoked"


class EnvironmentType(str, enum.Enum):
    """Server environment types."""
    PRODUCTION = "production"
    NON_PRODUCTION = "non_production"
    DEVELOPMENT = "development"
    DR = "dr"
    UAT = "uat"


class AccessRequest(Base):
    """Main access request table."""

    __tablename__ = "access_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(50), unique=True, nullable=False, index=True)

    # Requester
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Request Details
    access_type = Column(SAEnum(AccessType), nullable=False)
    environment = Column(SAEnum(EnvironmentType), nullable=False)
    purpose = Column(Text, nullable=False)
    business_justification = Column(Text, nullable=False)
    application_name = Column(String(255), nullable=True)
    project_name = Column(String(255), nullable=True)

    # Status
    status = Column(SAEnum(RequestStatus), default=RequestStatus.PENDING_APPROVAL, nullable=False, index=True)
    current_approval_step = Column(Integer, default=1)

    # Sudo Configuration
    sudo_expiry_date = Column(DateTime(timezone=True), nullable=True)
    is_renewal = Column(Boolean, default=False)
    original_request_id = Column(Integer, ForeignKey("access_requests.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    approved_at = Column(DateTime(timezone=True), nullable=True)
    provisioned_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    requester = relationship("User", back_populates="access_requests", foreign_keys=[requester_id])
    servers = relationship("RequestServer", back_populates="request", cascade="all, delete-orphan")
    approval_steps = relationship("ApprovalStep", back_populates="request", cascade="all, delete-orphan")
    provisioning_tasks = relationship("ProvisioningTask", back_populates="request", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AccessRequest(id={self.id}, request_id='{self.request_id}', status='{self.status}')>"


class RequestServer(Base):
    """Servers associated with an access request."""

    __tablename__ = "request_servers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey("access_requests.id"), nullable=False)

    # Server Details
    hostname = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)

    # Provisioning Status
    provisioning_status = Column(String(50), default="pending")
    provisioning_message = Column(Text, nullable=True)
    provisioned_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    request = relationship("AccessRequest", back_populates="servers")

    def __repr__(self):
        return f"<RequestServer(id={self.id}, hostname='{self.hostname}', ip='{self.ip_address}')>"
