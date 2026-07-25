"""
Admin Routes.
Dashboard, configuration, user management, SSH keys, scripts, etc.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func, Integer
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



# --- Email Template Editor (#11) ---

@router.get("/email-templates")
async def list_email_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """List all email templates."""
    result = await db.execute(select(EmailTemplate).order_by(EmailTemplate.template_type))
    templates = result.scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "template_type": t.template_type,
            "subject": t.subject,
            "body_html": t.body_html,
            "is_active": t.is_active,
            "variables": t.variables,
            "updated_at": t.updated_at,
        }
        for t in templates
    ]


@router.post("/email-templates")
async def create_email_template(
    name: str,
    template_type: str,
    subject: str,
    body_html: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Create a new email template."""
    template = EmailTemplate(
        name=name,
        template_type=template_type,
        subject=subject,
        body_html=body_html,
        is_active=True,
    )
    db.add(template)
    await db.flush()

    audit = AuditLog(
        user_id=current_user.id,
        user_email=current_user.email,
        action="email_template_created",
        resource_type="email_template",
        resource_id=str(template.id),
    )
    db.add(audit)
    return {"message": f"Template '{name}' created", "id": template.id}


@router.put("/email-templates/{template_id}")
async def update_email_template(
    template_id: int,
    name: Optional[str] = None,
    subject: Optional[str] = None,
    body_html: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Update an existing email template."""
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if name is not None:
        template.name = name
    if subject is not None:
        template.subject = subject
    if body_html is not None:
        template.body_html = body_html
    if is_active is not None:
        template.is_active = is_active

    audit = AuditLog(
        user_id=current_user.id,
        user_email=current_user.email,
        action="email_template_updated",
        resource_type="email_template",
        resource_id=str(template_id),
    )
    db.add(audit)
    return {"message": f"Template '{template.name}' updated"}


@router.delete("/email-templates/{template_id}")
async def delete_email_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Delete an email template."""
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    await db.delete(template)
    return {"message": f"Template deleted"}


# --- Dashboard Chart Data (#9) ---

@router.get("/charts/monthly-requests")
async def chart_monthly_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Monthly request counts for chart display."""
    result = await db.execute(
        select(
            func.strftime("%Y-%m", AccessRequest.created_at).label("month"),
            func.count(AccessRequest.id).label("total"),
            func.sum(func.cast(AccessRequest.status == RequestStatus.PROVISIONED, Integer)).label("approved"),
            func.sum(func.cast(AccessRequest.status == RequestStatus.REJECTED, Integer)).label("rejected"),
        )
        .group_by("month")
        .order_by("month")
    )
    rows = result.all()
    return [{"month": r.month, "total": r.total, "approved": r.approved or 0, "rejected": r.rejected or 0} for r in rows]


@router.get("/charts/top-servers")
async def chart_top_servers(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Top requested server IPs."""
    from ...models.request import RequestServer
    result = await db.execute(
        select(
            RequestServer.ip_address,
            func.count(RequestServer.id).label("request_count"),
        )
        .where(RequestServer.ip_address.isnot(None))
        .group_by(RequestServer.ip_address)
        .order_by(func.count(RequestServer.id).desc())
        .limit(limit)
    )
    rows = result.all()
    return [{"ip_address": r.ip_address, "request_count": r.request_count} for r in rows]


@router.get("/charts/approval-sla")
async def chart_approval_sla(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Average approval time per step."""
    from ...models.approval import ApprovalStep, ApprovalStatus
    result = await db.execute(
        select(ApprovalStep)
        .where(ApprovalStep.status == ApprovalStatus.APPROVED, ApprovalStep.completed_at.isnot(None))
    )
    steps = result.scalars().all()

    step_times = {}
    for step in steps:
        name = step.step_name
        if step.completed_at and step.created_at:
            hours = (step.completed_at - step.created_at).total_seconds() / 3600
            if name not in step_times:
                step_times[name] = []
            step_times[name].append(hours)

    return [
        {
            "step_name": name,
            "avg_hours": round(sum(times) / len(times), 1) if times else 0,
            "count": len(times),
        }
        for name, times in step_times.items()
    ]


# --- Password/SSH Key Rotation Reminders (#10) ---

@router.get("/rotation-status")
async def get_rotation_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Check rotation status of sensitive credentials.
    Returns warnings for SSH keys and emergency admin password that
    haven't been updated within the configured rotation period.
    """
    from datetime import datetime, timezone, timedelta

    ROTATION_DAYS = 90  # Recommended rotation period
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=ROTATION_DAYS)

    warnings = []

    # Check SSH keys
    result = await db.execute(select(SSHKey).where(SSHKey.is_active == True))
    ssh_keys = result.scalars().all()
    for key in ssh_keys:
        age_days = (now - key.created_at).days if key.created_at else 999
        updated_days = (now - key.updated_at).days if key.updated_at else age_days
        if key.created_at and key.created_at < threshold:
            warnings.append({
                "type": "ssh_key",
                "name": key.name,
                "last_updated": key.updated_at.isoformat() if key.updated_at else key.created_at.isoformat(),
                "age_days": age_days,
                "status": "overdue" if age_days > ROTATION_DAYS * 2 else "due",
                "message": f"SSH key '{key.name}' is {age_days} days old. Recommended rotation: every {ROTATION_DAYS} days.",
            })

    # Check emergency admin (we can only check if it was ever changed via audit log)
    admin_audit = await db.execute(
        select(AuditLog)
        .where(AuditLog.action == "config_updated", AuditLog.resource_id == "EMERGENCY_ADMIN_PASSWORD")
        .order_by(AuditLog.created_at.desc())
    )
    last_password_change = admin_audit.scalar_one_or_none()
    if not last_password_change or (last_password_change.created_at and last_password_change.created_at < threshold):
        last_changed = last_password_change.created_at.isoformat() if last_password_change else "Never"
        warnings.append({
            "type": "emergency_password",
            "name": "Emergency Admin Password",
            "last_updated": last_changed,
            "age_days": (now - last_password_change.created_at).days if last_password_change and last_password_change.created_at else 999,
            "status": "overdue",
            "message": f"Emergency admin password last changed: {last_changed}. Recommend rotation every {ROTATION_DAYS} days.",
        })

    return {
        "rotation_period_days": ROTATION_DAYS,
        "warnings": warnings,
        "total_warnings": len(warnings),
        "status": "healthy" if not warnings else "action_required",
    }


# --- Secrets Manager Status ---

@router.get("/secrets-status")
async def get_secrets_status(
    current_user: User = Depends(get_current_admin_user),
):
    """
    Check AWS Secrets Manager integration status.
    Shows which secrets source is active and health status.
    Does NOT expose secret values.
    """
    from ...core.secrets_manager import is_secrets_manager_enabled, SENSITIVE_KEYS
    from ...core.config import settings
    import os

    sm_enabled = is_secrets_manager_enabled()

    # Check which sensitive keys are configured (without exposing values)
    key_status = {}
    for key in SENSITIVE_KEYS:
        value = getattr(settings, key, None) or os.environ.get(key, "")
        if value:
            key_status[key] = {
                "configured": True,
                "source": "secrets_manager" if sm_enabled else "environment",
                "length": len(value),
            }
        else:
            key_status[key] = {
                "configured": False,
                "source": None,
                "length": 0,
            }

    all_configured = all(v["configured"] for v in key_status.values())

    return {
        "secrets_manager_enabled": sm_enabled,
        "secret_name": settings.AWS_SECRETS_MANAGER_SECRET_NAME if sm_enabled else None,
        "region": settings.AWS_SECRETS_MANAGER_REGION if sm_enabled else None,
        "all_secrets_configured": all_configured,
        "keys": key_status,
        "recommendation": (
            "All secrets are loaded from AWS Secrets Manager"
            if sm_enabled and all_configured
            else "Enable AWS Secrets Manager for production (set AWS_SECRETS_MANAGER_ENABLED=true)"
            if not sm_enabled
            else "Some secrets are missing - check AWS Secrets Manager configuration"
        ),
    }
