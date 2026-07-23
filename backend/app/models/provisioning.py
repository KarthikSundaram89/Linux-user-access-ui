"""Provisioning Models."""

import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, Enum as SAEnum, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from ..core.database import Base


class ProvisioningStatus(str, enum.Enum):
    """Status of a provisioning task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class ProvisioningTask(Base):
    """Provisioning task for a specific server."""

    __tablename__ = "provisioning_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey("access_requests.id"), nullable=False)
    server_id = Column(Integer, ForeignKey("request_servers.id"), nullable=False)

    # Task Details
    hostname = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    username = Column(String(100), nullable=False)

    # Status
    status = Column(SAEnum(ProvisioningStatus), default=ProvisioningStatus.PENDING)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    # Results
    output = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    request = relationship("AccessRequest", back_populates="provisioning_tasks")
    logs = relationship("ProvisioningLog", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ProvisioningTask(id={self.id}, host='{self.hostname}', status='{self.status}')>"


class ProvisioningLog(Base):
    """Detailed logs for provisioning execution."""

    __tablename__ = "provisioning_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("provisioning_tasks.id"), nullable=False)

    # Log Details
    level = Column(String(20), default="info")
    message = Column(Text, nullable=False)
    command = Column(Text, nullable=True)
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    task = relationship("ProvisioningTask", back_populates="logs")

    def __repr__(self):
        return f"<ProvisioningLog(id={self.id}, level='{self.level}')>"
