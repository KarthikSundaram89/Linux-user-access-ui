"""Audit Log Model - Immutable audit trail."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON

from ..core.database import Base


class AuditLog(Base):
    """
    Immutable audit log table.
    Every significant action in the system is logged here.
    These records should never be edited or deleted.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Who
    user_id = Column(Integer, nullable=True)
    user_email = Column(String(255), nullable=True)
    user_name = Column(String(255), nullable=True)

    # What
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    # Context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    request_method = Column(String(10), nullable=True)
    request_path = Column(String(500), nullable=True)

    # Details (JSON for flexible data)
    details = Column(JSON, nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}', user='{self.user_email}')>"
