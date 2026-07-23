"""
Approval Engine Service.
Manages the complete approval workflow lifecycle.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.approval import ApprovalStep, ApprovalAction, ApprovalStatus, ApprovalType
from ...models.request import AccessRequest, RequestStatus
from ...models.configuration import ApprovalWorkflowConfig
from ...models.user import User

logger = logging.getLogger(__name__)


class ApprovalEngine:
    """
    Configurable approval workflow engine.
    Supports sequential, parallel approvals, delegation, escalation, and timeout.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_approval_workflow(self, request: AccessRequest) -> List[ApprovalStep]:
        """
        Create approval steps for a new request based on workflow configuration.
        """
        # Load workflow configuration from database
        result = await self.db.execute(
            select(ApprovalWorkflowConfig)
            .where(ApprovalWorkflowConfig.is_active == True)
            .order_by(ApprovalWorkflowConfig.step_order)
        )
        workflow_configs = result.scalars().all()

        if not workflow_configs:
            # Use default workflow if nothing configured
            workflow_configs = await self._get_default_workflow(request)

        steps = []
        for config in workflow_configs:
            approver_email = await self._resolve_approver(config, request)

            step = ApprovalStep(
                request_id=request.id,
                step_order=config.step_order if hasattr(config, 'step_order') else config["step_order"],
                step_name=config.name if hasattr(config, 'name') else config["name"],
                approval_type=ApprovalType(config.approval_type if hasattr(config, 'approval_type') else config["approval_type"]),
                approver_email=approver_email,
                approver_role=config.approver_role if hasattr(config, 'approver_role') else config["approver_role"],
                timeout_hours=config.timeout_hours if hasattr(config, 'timeout_hours') else config["timeout_hours"],
                is_active=(config.step_order if hasattr(config, 'step_order') else config["step_order"]) == 1,
            )
            self.db.add(step)
            steps.append(step)

        await self.db.flush()
        return steps

    async def _resolve_approver(self, config, request: AccessRequest) -> str:
        """Resolve the approver email based on config type."""
        approver_type = config.approver_type if hasattr(config, 'approver_type') else config["approver_type"]

        if approver_type == "manager":
            # Get requester's manager
            result = await self.db.execute(
                select(User).where(User.id == request.requester_id)
            )
            requester = result.scalar_one_or_none()
            if requester and requester.manager_email:
                return requester.manager_email
            return "manager@company.com"

        elif approver_type == "specific_user":
            approver_email = config.approver_email if hasattr(config, 'approver_email') else config["approver_email"]
            return approver_email or "admin@company.com"

        elif approver_type == "role":
            # Find user with matching role
            approver_role = config.approver_role if hasattr(config, 'approver_role') else config["approver_role"]
            result = await self.db.execute(
                select(User).where(User.role == approver_role, User.is_active == True)
            )
            user = result.scalar_one_or_none()
            if user:
                return user.email
            return f"{approver_role}@company.com"

        return "admin@company.com"

    async def _get_default_workflow(self, request: AccessRequest) -> list:
        """Return default approval workflow configuration."""
        return [
            {
                "step_order": 1,
                "name": "Reporting Manager Approval",
                "approver_role": "reporting_manager",
                "approver_type": "manager",
                "approver_email": None,
                "approval_type": "sequential",
                "timeout_hours": 48,
            },
            {
                "step_order": 2,
                "name": "Cloud Team Manager Approval",
                "approver_role": "cloud_manager",
                "approver_type": "role",
                "approver_email": None,
                "approval_type": "sequential",
                "timeout_hours": 48,
            },
            {
                "step_order": 3,
                "name": "Information Security Approval",
                "approver_role": "infosec",
                "approver_type": "role",
                "approver_email": None,
                "approval_type": "sequential",
                "timeout_hours": 48,
            },
        ]

    async def process_approval_action(
        self,
        step_id: int,
        approver_id: int,
        action: str,
        comments: Optional[str] = None,
        delegate_to_email: Optional[str] = None,
    ) -> dict:
        """
        Process an approval action (approve, reject, send_back, delegate).
        Returns dict with result info.
        """
        # Get the step
        result = await self.db.execute(
            select(ApprovalStep).where(ApprovalStep.id == step_id)
        )
        step = result.scalar_one_or_none()

        if not step:
            return {"success": False, "error": "Approval step not found"}

        if not step.is_active:
            return {"success": False, "error": "This approval step is not currently active"}

        if step.status != ApprovalStatus.PENDING:
            return {"success": False, "error": "This step has already been processed"}

        # Record the action
        approval_action = ApprovalAction(
            step_id=step_id,
            approver_id=approver_id,
            action=ApprovalStatus(action),
            comments=comments,
        )
        self.db.add(approval_action)

        # Process based on action type
        if action == "approved":
            step.status = ApprovalStatus.APPROVED
            step.completed_at = datetime.now(timezone.utc)
            step.is_active = False

            # Advance to next step or complete
            return await self._advance_workflow(step)

        elif action == "rejected":
            step.status = ApprovalStatus.REJECTED
            step.completed_at = datetime.now(timezone.utc)
            step.is_active = False

            # Reject the entire request
            request_result = await self.db.execute(
                select(AccessRequest).where(AccessRequest.id == step.request_id)
            )
            request = request_result.scalar_one()
            request.status = RequestStatus.REJECTED

            return {"success": True, "result": "rejected", "request_id": request.request_id}

        elif action == "sent_back":
            step.status = ApprovalStatus.SENT_BACK
            step.completed_at = datetime.now(timezone.utc)
            step.is_active = False

            # Move back to previous step or requester
            return await self._send_back(step)

        elif action == "delegated":
            if not delegate_to_email:
                return {"success": False, "error": "Delegate email required"}

            step.delegated_to_email = delegate_to_email
            step.delegated_at = datetime.now(timezone.utc)
            step.status = ApprovalStatus.DELEGATED

            # Create new step for delegate
            new_step = ApprovalStep(
                request_id=step.request_id,
                step_order=step.step_order,
                step_name=f"{step.step_name} (Delegated)",
                approval_type=step.approval_type,
                approver_email=delegate_to_email,
                approver_role=step.approver_role,
                timeout_hours=step.timeout_hours,
                is_active=True,
            )
            self.db.add(new_step)

            return {"success": True, "result": "delegated", "delegated_to": delegate_to_email}

        return {"success": False, "error": "Invalid action"}

    async def _advance_workflow(self, completed_step: ApprovalStep) -> dict:
        """Advance workflow to the next step after approval."""
        # Get all steps for this request
        result = await self.db.execute(
            select(ApprovalStep)
            .where(ApprovalStep.request_id == completed_step.request_id)
            .order_by(ApprovalStep.step_order)
        )
        all_steps = result.scalars().all()

        # Find next pending step
        next_step = None
        for step in all_steps:
            if step.status == ApprovalStatus.PENDING and step.id != completed_step.id:
                next_step = step
                break

        if next_step:
            # Activate next step
            next_step.is_active = True

            # Update request
            request_result = await self.db.execute(
                select(AccessRequest).where(AccessRequest.id == completed_step.request_id)
            )
            request = request_result.scalar_one()
            request.current_approval_step = next_step.step_order

            return {
                "success": True,
                "result": "next_step",
                "next_step": next_step.step_name,
                "approver": next_step.approver_email,
            }
        else:
            # All steps approved - mark request as approved
            request_result = await self.db.execute(
                select(AccessRequest).where(AccessRequest.id == completed_step.request_id)
            )
            request = request_result.scalar_one()
            request.status = RequestStatus.APPROVED
            request.approved_at = datetime.now(timezone.utc)

            return {
                "success": True,
                "result": "fully_approved",
                "request_id": request.request_id,
            }

    async def _send_back(self, step: ApprovalStep) -> dict:
        """Send request back to previous step or requester."""
        # Get previous step
        result = await self.db.execute(
            select(ApprovalStep)
            .where(
                ApprovalStep.request_id == step.request_id,
                ApprovalStep.step_order < step.step_order,
            )
            .order_by(ApprovalStep.step_order.desc())
        )
        previous_step = result.scalar_one_or_none()

        if previous_step:
            # Reset previous step
            previous_step.status = ApprovalStatus.PENDING
            previous_step.is_active = True
            previous_step.completed_at = None
            return {"success": True, "result": "sent_back", "to_step": previous_step.step_name}
        else:
            # No previous step - send back to requester
            return {"success": True, "result": "sent_back_to_requester"}

    async def get_pending_approvals_for_user(self, user_email: str) -> List[ApprovalStep]:
        """Get all pending approval steps assigned to a user."""
        result = await self.db.execute(
            select(ApprovalStep)
            .where(
                ApprovalStep.approver_email == user_email,
                ApprovalStep.status == ApprovalStatus.PENDING,
                ApprovalStep.is_active == True,
            )
        )
        return result.scalars().all()

    async def check_timeouts(self):
        """Check for timed-out approval steps and escalate."""
        from datetime import timedelta

        result = await self.db.execute(
            select(ApprovalStep).where(
                ApprovalStep.status == ApprovalStatus.PENDING,
                ApprovalStep.is_active == True,
            )
        )
        steps = result.scalars().all()

        now = datetime.now(timezone.utc)
        for step in steps:
            elapsed = (now - step.created_at).total_seconds() / 3600
            if elapsed > step.timeout_hours:
                step.status = ApprovalStatus.TIMED_OUT
                step.is_active = False
                step.escalated_at = now
                logger.warning(f"Approval step {step.id} timed out after {elapsed:.1f} hours")
