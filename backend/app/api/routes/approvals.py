"""
Approval Routes.
Handles approval actions, listing pending approvals, and approval history.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.database import get_db
from ...models.user import User
from ...models.request import AccessRequest
from ...models.approval import ApprovalStep, ApprovalStatus
from ...models.audit import AuditLog
from ...schemas.approval import (
    ApprovalActionCreate,
    ApprovalStepResponse,
    ApprovalHistoryResponse,
)
from ..dependencies.auth import get_current_user, get_current_approver
from ...services.approval.approval_engine import ApprovalEngine
from ...services.notification.email_service import email_service
from ...services.provisioning.provisioner import ProvisioningService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/approvals", tags=["Approvals"])



@router.get("/pending")
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all pending approvals for the current user."""
    engine = ApprovalEngine(db)
    steps = await engine.get_pending_approvals_for_user(current_user.email)

    results = []
    for step in steps:
        # Get the associated request
        req_result = await db.execute(
            select(AccessRequest).where(AccessRequest.id == step.request_id)
        )
        request = req_result.scalar_one_or_none()
        results.append({
            "step": ApprovalStepResponse.model_validate(step),
            "request_id": request.request_id if request else None,
            "requester_email": None,
        })

    return {"pending_approvals": results, "count": len(results)}


@router.post("/{step_id}/action")
async def process_approval(
    step_id: int,
    action_data: ApprovalActionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approver),
):
    """Process an approval action (approve, reject, send_back, delegate)."""
    engine = ApprovalEngine(db)
    result = await engine.process_approval_action(
        step_id=step_id,
        approver_id=current_user.id,
        action=action_data.action,
        comments=action_data.comments,
        delegate_to_email=action_data.delegate_to_email,
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Action failed"))

    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        user_email=current_user.email,
        user_name=current_user.display_name,
        action=f"approval_{action_data.action}",
        resource_type="approval_step",
        resource_id=str(step_id),
        description=f"Approval action: {action_data.action}",
        details={"comments": action_data.comments},
    )
    db.add(audit)

    # If fully approved, trigger provisioning
    if result.get("result") == "fully_approved":
        req_result = await db.execute(
            select(AccessRequest)
            .options(selectinload(AccessRequest.servers))
            .where(AccessRequest.request_id == result["request_id"])
        )
        request = req_result.scalar_one()
        provisioner = ProvisioningService(db)
        background_tasks.add_task(provisioner.provision_request, request)

    return {"message": "Action processed", "result": result}


@router.get("/history/{request_id}")
async def get_approval_history(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full approval history for a request."""
    # Get request
    req_result = await db.execute(
        select(AccessRequest).where(AccessRequest.request_id == request_id)
    )
    request = req_result.scalar_one_or_none()
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    # Get steps with actions
    steps_result = await db.execute(
        select(ApprovalStep)
        .options(selectinload(ApprovalStep.actions))
        .where(ApprovalStep.request_id == request.id)
        .order_by(ApprovalStep.step_order)
    )
    steps = steps_result.scalars().all()

    return {
        "request_id": request_id,
        "steps": [ApprovalStepResponse.model_validate(s) for s in steps],
    }
