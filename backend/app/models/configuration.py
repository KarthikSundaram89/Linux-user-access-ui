"""Configuration Models - Admin-configurable settings stored in database."""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, JSON

from ..core.database import Base


class SystemConfiguration(Base):
    """Key-value configuration stored in database, manageable via Admin UI."""

    __tablename__ = "system_configurations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(50), default="string")  # string, integer, boolean, json
    category = Column(String(100), nullable=False)  # azure_ad, smtp, ssh, sudo, branding, etc.
    description = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False)  # If true, value is encrypted

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<SystemConfiguration(key='{self.key}', category='{self.category}')>"


class ApprovalWorkflowConfig(Base):
    """Configurable approval workflow steps."""

    __tablename__ = "approval_workflow_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    step_order = Column(Integer, nullable=False)
    approver_role = Column(String(100), nullable=False)
    approver_type = Column(String(50), nullable=False)  # role, specific_user, manager
    approver_email = Column(String(255), nullable=True)  # For specific_user type
    approval_type = Column(String(50), default="sequential")  # sequential, parallel
    timeout_hours = Column(Integer, default=48)
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<ApprovalWorkflowConfig(name='{self.name}', order={self.step_order})>"


class SSHKey(Base):
    """SSH keys for server authentication."""

    __tablename__ = "ssh_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    key_type = Column(String(50), nullable=False)  # rsa, ecdsa, ed25519
    private_key_encrypted = Column(Text, nullable=False)  # Encrypted with Fernet
    passphrase_encrypted = Column(Text, nullable=True)  # Encrypted if present
    fingerprint = Column(String(255), nullable=True)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Associated servers (optional - None means all servers)
    server_pattern = Column(String(500), nullable=True)  # Glob pattern or comma-separated

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<SSHKey(id={self.id}, name='{self.name}', type='{self.key_type}')>"


class ProvisioningScript(Base):
    """Configurable provisioning scripts."""

    __tablename__ = "provisioning_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    script_type = Column(String(50), nullable=False)  # user_creation, sudo_assignment, user_removal, sudo_removal, renewal
    script_content = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    # Variables supported: $username, $hostname, $expiry_date, $request_id, $groups
    variables = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<ProvisioningScript(id={self.id}, name='{self.name}', type='{self.script_type}')>"


class EmailTemplate(Base):
    """Configurable email templates."""

    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    template_type = Column(String(100), nullable=False)  # request_submitted, approval_pending, etc.
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    # Variables available in template
    variables = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<EmailTemplate(id={self.id}, name='{self.name}')>"
