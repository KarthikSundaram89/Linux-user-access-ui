"""
Access Request Routes.
Handles creation, listing, updating, and cancellation of access requests.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.database import get_db
from ...core.security import generate_request_id
from ...models.user import User
from ...models.request import AccessRequest, RequestServer, RequestStatus, AccessType, EnvironmentType
from ...models.audit import AuditLog
from ...schemas.request import (
    AccessRequestCreate,
    AccessRequestResponse,
    AccessRequestListResponse,
    ServerResponse,
)
from ..dependencies.auth import get_current_user
from ...services.approval.approval_engine import ApprovalEngine
from ...services.notification.email_service import email_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/requests", tags=["Requests"])



@router.post("/", response_model=AccessRequestResponse)
async def create_request(
    request_data: AccessRequestCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new access request."""
    # Create the access request
    access_request = AccessRequest(
        request_id=generate_request_id(),
        requester_id=current_user.id,
        access_type=AccessType(request_data.access_type),
        environment=EnvironmentType(request_data.environment),
        purpose=request_data.purpose,
        business_justification=request_data.business_justification,
        application_name=request_data.application_name,
        project_name=request_data.project_name,
        is_renewal=request_data.is_renewal,
        original_request_id=request_data.original_request_id,
        status=RequestStatus.PENDING_APPROVAL,
    )
    db.add(access_request)
    await db.flush()

    # Add servers
    for server_input in request_data.servers:
        server = RequestServer(
            request_id=access_request.id,
            hostname=server_input.hostname,
            ip_address=server_input.ip_address,
        )
        db.add(server)

    await db.flush()

    # Create approval workflow
    approval_engine = ApprovalEngine(db)
    await approval_engine.create_approval_workflow(access_request)

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        user_email=current_user.email,
        user_name=current_user.display_name,
        action="request_created",
        resource_type="access_request",
        resource_id=access_request.request_id,
        description=f"Created {request_data.access_type} request",
    )
    db.add(audit)

    # Send notification in background
    background_tasks.add_task(
        email_service.notify_request_submitted,
        {
            "request_id": access_request.request_id,
            "requester_email": current_user.email,
            "access_type": request_data.access_type,
            "servers": ", ".join(
                s.hostname or s.ip_address for s in request_data.servers
            ),
        },
    )

    # Reload with relationships
    await db.refresh(access_request, ["servers"])

    return _format_request_response(access_request, current_user)



@router.get("/", response_model=AccessRequestListResponse)
async def list_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List access requests for the current user."""
    query = select(AccessRequest).options(selectinload(AccessRequest.servers))

    # Non-admins see only their requests
    from ...models.user import UserRole
    admin_roles = [UserRole.ADMINISTRATOR, UserRole.SUPER_ADMINISTRATOR]
    if current_user.role not in admin_roles:
        query = query.where(AccessRequest.requester_id == current_user.id)

    if status:
        query = query.where(AccessRequest.status == RequestStatus(status))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    query = query.order_by(AccessRequest.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    requests = result.scalars().all()

    items = [_format_request_response(r, current_user) for r in requests]

    return AccessRequestListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{request_id}", response_model=AccessRequestResponse)
async def get_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific access request by ID."""
    result = await db.execute(
        select(AccessRequest)
        .options(selectinload(AccessRequest.servers))
        .where(AccessRequest.request_id == request_id)
    )
    access_request = result.scalar_one_or_none()

    if not access_request:
        raise HTTPException(status_code=404, detail="Request not found")

    return _format_request_response(access_request, current_user)


@router.post("/{request_id}/cancel")
async def cancel_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a pending request."""
    result = await db.execute(
        select(AccessRequest).where(AccessRequest.request_id == request_id)
    )
    access_request = result.scalar_one_or_none()

    if not access_request:
        raise HTTPException(status_code=404, detail="Request not found")

    if access_request.requester_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your request")

    if access_request.status != RequestStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail="Can only cancel pending requests")

    access_request.status = RequestStatus.CANCELLED
    access_request.cancelled_at = datetime.now(timezone.utc)

    audit = AuditLog(
        user_id=current_user.id,
        user_email=current_user.email,
        action="request_cancelled",
        resource_type="access_request",
        resource_id=request_id,
    )
    db.add(audit)

    return {"message": "Request cancelled", "request_id": request_id}


def _format_request_response(request: AccessRequest, user: User) -> AccessRequestResponse:
    """Format an AccessRequest model into response schema."""
    servers = [
        ServerResponse(
            id=s.id,
            hostname=s.hostname,
            ip_address=s.ip_address,
            provisioning_status=s.provisioning_status,
            provisioning_message=s.provisioning_message,
            provisioned_at=s.provisioned_at,
        )
        for s in (request.servers or [])
    ]

    return AccessRequestResponse(
        id=request.id,
        request_id=request.request_id,
        access_type=request.access_type.value,
        environment=request.environment.value,
        purpose=request.purpose,
        business_justification=request.business_justification,
        application_name=request.application_name,
        project_name=request.project_name,
        status=request.status.value,
        current_approval_step=request.current_approval_step,
        sudo_expiry_date=request.sudo_expiry_date,
        is_renewal=request.is_renewal,
        servers=servers,
        requester_name=user.display_name if user else None,
        requester_email=user.email if user else None,
        created_at=request.created_at,
        updated_at=request.updated_at,
        approved_at=request.approved_at,
        provisioned_at=request.provisioned_at,
    )
