"""
Admin Routes.
Dashboard, configuration, user management, SSH keys, scripts, etc.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.security import encrypt_value
from ...models.user import User, UserRole
from ...models.request import AccessRequest, RequestStatus, AccessType
from ...models.configuration import (
    SystemConfiguration,
    ApprovalWorkflowConfig,
    SSHKey,
    ProvisioningScript,
    EmailTemplate,
)
from ...models.audit import AuditLog
from ...schemas.user import UserResponse, UserUpdate
from ...schemas.common import DashboardStats
from ..dependencies.auth import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin"])



@router.get("/dashboard", response_model=DashboardStats)
async def get_admin_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Get admin dashboard statistics."""
    from datetime import datetime, timezone, timedelta
    from ...core.config import settings

    now = datetime.now(timezone.utc)
    reminder_threshold = now + timedelta(days=settings.SUDO_REMINDER_DAYS)

    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    pending = (await db.execute(
        select(func.count(AccessRequest.id))
        .where(AccessRequest.status == RequestStatus.PENDING_APPROVAL)
    )).scalar()
    approved = (await db.execute(
        select(func.count(AccessRequest.id))
        .where(AccessRequest.status == RequestStatus.PROVISIONED)
    )).scalar()
    rejected = (await db.execute(
        select(func.count(AccessRequest.id))
        .where(AccessRequest.status == RequestStatus.REJECTED)
    )).scalar()
    failures = (await db.execute(
        select(func.count(AccessRequest.id))
        .where(AccessRequest.status == RequestStatus.PROVISIONING_FAILED)
    )).scalar()
    expiring = (await db.execute(
        select(func.count(AccessRequest.id))
        .where(
            AccessRequest.sudo_expiry_date <= reminder_threshold,
            AccessRequest.sudo_expiry_date > now,
            AccessRequest.status == RequestStatus.PROVISIONED,
        )
    )).scalar()
    expired = (await db.execute(
        select(func.count(AccessRequest.id))
        .where(
            AccessRequest.sudo_expiry_date <= now,
            AccessRequest.status == RequestStatus.REVOKED,
        )
    )).scalar()

    return DashboardStats(
        total_users=total_users or 0,
        pending_requests=pending or 0,
        approved_requests=approved or 0,
        rejected_requests=rejected or 0,
        provisioning_failures=failures or 0,
        servers_managed=0,
        expiring_sudo=expiring or 0,
        expired_sudo=expired or 0,
    )



@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """List all users with pagination."""
    total = (await db.execute(select(func.count(User.id)))).scalar()
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    users = result.scalars().all()
    return {
        "items": [UserResponse.model_validate(u) for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Update a user's role or status."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if update_data.role:
        user.role = UserRole(update_data.role)
    if update_data.is_active is not None:
        user.is_active = update_data.is_active
    if update_data.display_name:
        user.display_name = update_data.display_name

    audit = AuditLog(
        user_id=current_user.id,
        user_email=current_user.email,
        action="user_updated",
        resource_type="user",
        resource_id=str(user_id),
        details=update_data.model_dump(exclude_none=True),
    )
    db.add(audit)
    return UserResponse.model_validate(user)


@router.get("/config")
async def get_configurations(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Get system configurations."""
    query = select(SystemConfiguration)
    if category:
        query = query.where(SystemConfiguration.category == category)
    result = await db.execute(query.order_by(SystemConfiguration.category))
    configs = result.scalars().all()
    return [
        {
            "id": c.id,
            "key": c.key,
            "value": "***" if c.is_secret else c.value,
            "category": c.category,
            "description": c.description,
        }
        for c in configs
    ]


@router.put("/config/{key}")
async def update_configuration(
    key: str,
    value: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Update a system configuration value."""
    result = await db.execute(
        select(SystemConfiguration).where(SystemConfiguration.key == key)
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    if config.is_secret:
        config.value = encrypt_value(value)
    else:
        config.value = value

    audit = AuditLog(
        user_id=current_user.id,
        user_email=current_user.email,
        action="config_updated",
        resource_type="configuration",
        resource_id=key,
    )
    db.add(audit)
    return {"message": f"Configuration '{key}' updated"}



@router.post("/ssh-keys")
async def upload_ssh_key(
    name: str,
    key_type: str,
    private_key: UploadFile = File(...),
    passphrase: Optional[str] = None,
    is_default: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Upload an SSH private key."""
    key_content = await private_key.read()
    key_str = key_content.decode("utf-8")

    encrypted_key = encrypt_value(key_str)
    encrypted_passphrase = encrypt_value(passphrase) if passphrase else None

    ssh_key = SSHKey(
        name=name,
        key_type=key_type,
        private_key_encrypted=encrypted_key,
        passphrase_encrypted=encrypted_passphrase,
        is_default=is_default,
    )
    db.add(ssh_key)

    audit = AuditLog(
        user_id=current_user.id,
        user_email=current_user.email,
        action="ssh_key_uploaded",
        resource_type="ssh_key",
        description=f"SSH key '{name}' uploaded",
    )
    db.add(audit)
    await db.flush()
    return {"message": f"SSH key '{name}' uploaded", "id": ssh_key.id}


@router.get("/ssh-keys")
async def list_ssh_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """List all SSH keys (without private key content)."""
    result = await db.execute(select(SSHKey))
    keys = result.scalars().all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "key_type": k.key_type,
            "is_default": k.is_default,
            "is_active": k.is_active,
            "created_at": k.created_at,
        }
        for k in keys
    ]


@router.get("/scripts")
async def list_scripts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """List all provisioning scripts."""
    result = await db.execute(select(ProvisioningScript))
    scripts = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "script_type": s.script_type,
            "script_content": s.script_content,
            "is_active": s.is_active,
            "variables": s.variables,
        }
        for s in scripts
    ]


@router.post("/scripts")
async def create_script(
    name: str,
    script_type: str,
    script_content: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Create a provisioning script."""
    script = ProvisioningScript(
        name=name,
        script_type=script_type,
        script_content=script_content,
        is_active=True,
    )
    db.add(script)
    await db.flush()
    return {"message": f"Script '{name}' created", "id": script.id}


@router.get("/audit-logs")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """List audit logs with pagination."""
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)

    total = (await db.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar()

    query = query.order_by(AuditLog.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "items": [
            {
                "id": l.id,
                "user_email": l.user_email,
                "action": l.action,
                "resource_type": l.resource_type,
                "resource_id": l.resource_id,
                "description": l.description,
                "created_at": l.created_at,
            }
            for l in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/workflow")
async def get_workflow_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Get the approval workflow configuration."""
    result = await db.execute(
        select(ApprovalWorkflowConfig).order_by(ApprovalWorkflowConfig.step_order)
    )
    configs = result.scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "step_order": c.step_order,
            "approver_role": c.approver_role,
            "approver_type": c.approver_type,
            "approval_type": c.approval_type,
            "timeout_hours": c.timeout_hours,
            "is_active": c.is_active,
        }
        for c in configs
    ]
