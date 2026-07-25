"""
Unit tests for the Approval Engine service.
Tests workflow creation, step advancement, rejection, delegation, timeout.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.approval.approval_engine import ApprovalEngine
from app.models.request import AccessRequest, RequestServer, RequestStatus, AccessType, EnvironmentType
from app.models.approval import ApprovalStep, ApprovalAction, ApprovalStatus, ApprovalType
from app.models.configuration import ApprovalWorkflowConfig
from app.models.user import User, UserRole
from app.core.security import generate_request_id


@pytest_asyncio.fixture
async def approval_request(db_session: AsyncSession, test_user: User):
    """Create a request that needs approval."""
    request = AccessRequest(
        request_id=generate_request_id(),
        requester_id=test_user.id,
        access_type=AccessType.USER_ACCESS,
        environment=EnvironmentType.PRODUCTION,
        purpose="Need access for deployment tasks and maintenance",
        business_justification="Required for Q1 deployment operations to proceed",
        status=RequestStatus.PENDING_APPROVAL,
    )
    db_session.add(request)
    await db_session.flush()

    server = RequestServer(
        request_id=request.id,
        ip_address="10.10.10.5",
        provisioning_status="pending",
    )
    db_session.add(server)
    await db_session.flush()
    await db_session.refresh(request, ["servers"])
    return request


class TestWorkflowCreation:
    """Test approval workflow creation."""

    @pytest.mark.asyncio
    async def test_create_default_workflow(self, db_session, approval_request):
        """Should create default 3-step workflow when no config exists."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        assert len(steps) == 3
        assert steps[0].step_name == "Reporting Manager Approval"
        assert steps[1].step_name == "Cloud Team Manager Approval"
        assert steps[2].step_name == "Information Security Approval"

    @pytest.mark.asyncio
    async def test_first_step_is_active(self, db_session, approval_request):
        """First step should be active, others inactive."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        assert steps[0].is_active is True
        assert steps[1].is_active is False
        assert steps[2].is_active is False

    @pytest.mark.asyncio
    async def test_all_steps_start_as_pending(self, db_session, approval_request):
        """All steps should start with pending status."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        for step in steps:
            assert step.status == ApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_step_order_is_sequential(self, db_session, approval_request):
        """Steps should have sequential order numbers."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        orders = [s.step_order for s in steps]
        assert orders == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_workflow_with_configured_steps(self, db_session, approval_request):
        """Should use configured workflow when available."""
        # Add a custom workflow config
        config = ApprovalWorkflowConfig(
            name="Custom Step 1",
            step_order=1,
            approver_role="custom_role",
            approver_type="role",
            approval_type="sequential",
            timeout_hours=24,
            is_active=True,
        )
        db_session.add(config)
        await db_session.flush()

        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        assert len(steps) == 1
        assert steps[0].step_name == "Custom Step 1"


class TestApprovalAction:
    """Test processing approval actions."""

    @pytest.mark.asyncio
    async def test_approve_step(self, db_session, approval_request, approver_user):
        """Approving a step should mark it approved and advance."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        result = await engine.process_approval_action(
            step_id=steps[0].id,
            approver_id=approver_user.id,
            action="approved",
            comments="Looks good",
        )

        assert result["success"] is True
        assert result["result"] == "next_step"
        assert steps[0].status == ApprovalStatus.APPROVED
        assert steps[0].is_active is False

    @pytest.mark.asyncio
    async def test_approve_all_steps_fully_approves(self, db_session, approval_request, approver_user):
        """Approving all steps should mark request as fully approved."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        # Approve all 3 steps
        for step in steps:
            step.is_active = True
            step.status = ApprovalStatus.PENDING
        await db_session.flush()

        for step in steps:
            result = await engine.process_approval_action(
                step_id=step.id,
                approver_id=approver_user.id,
                action="approved",
            )

        assert result["result"] == "fully_approved"

        # Verify request status
        result_q = await db_session.execute(
            select(AccessRequest).where(AccessRequest.id == approval_request.id)
        )
        updated_request = result_q.scalar_one()
        assert updated_request.status == RequestStatus.APPROVED
        assert updated_request.approved_at is not None

    @pytest.mark.asyncio
    async def test_reject_step_rejects_request(self, db_session, approval_request, approver_user):
        """Rejecting a step should reject the entire request."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        result = await engine.process_approval_action(
            step_id=steps[0].id,
            approver_id=approver_user.id,
            action="rejected",
            comments="Not justified",
        )

        assert result["success"] is True
        assert result["result"] == "rejected"

        # Verify request is rejected
        result_q = await db_session.execute(
            select(AccessRequest).where(AccessRequest.id == approval_request.id)
        )
        updated_request = result_q.scalar_one()
        assert updated_request.status == RequestStatus.REJECTED

    @pytest.mark.asyncio
    async def test_process_inactive_step_fails(self, db_session, approval_request, approver_user):
        """Processing an inactive step should fail."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        # Try to approve step 2 (which is inactive)
        result = await engine.process_approval_action(
            step_id=steps[1].id,
            approver_id=approver_user.id,
            action="approved",
        )

        assert result["success"] is False
        assert "not currently active" in result["error"]

    @pytest.mark.asyncio
    async def test_process_already_processed_step_fails(self, db_session, approval_request, approver_user):
        """Processing an already-processed step should fail."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        # Approve the first step
        await engine.process_approval_action(
            step_id=steps[0].id,
            approver_id=approver_user.id,
            action="approved",
        )

        # Try to approve it again - it is now inactive and/or already processed
        result = await engine.process_approval_action(
            step_id=steps[0].id,
            approver_id=approver_user.id,
            action="approved",
        )

        assert result["success"] is False
        # Could be "not currently active" or "already been processed" depending on check order
        assert "not currently active" in result["error"] or "already been processed" in result["error"]

    @pytest.mark.asyncio
    async def test_nonexistent_step_fails(self, db_session, approver_user):
        """Processing a non-existent step should fail."""
        engine = ApprovalEngine(db_session)
        result = await engine.process_approval_action(
            step_id=99999,
            approver_id=approver_user.id,
            action="approved",
        )

        assert result["success"] is False
        assert "not found" in result["error"]


class TestDelegation:
    """Test delegation of approval steps."""

    @pytest.mark.asyncio
    async def test_delegate_creates_new_step(self, db_session, approval_request, approver_user):
        """Delegating should create a new step for the delegate."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        result = await engine.process_approval_action(
            step_id=steps[0].id,
            approver_id=approver_user.id,
            action="delegated",
            delegate_to_email="delegate@company.com",
        )

        assert result["success"] is True
        assert result["result"] == "delegated"
        assert result["delegated_to"] == "delegate@company.com"

    @pytest.mark.asyncio
    async def test_delegate_without_email_fails(self, db_session, approval_request, approver_user):
        """Delegating without providing an email should fail."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        result = await engine.process_approval_action(
            step_id=steps[0].id,
            approver_id=approver_user.id,
            action="delegated",
            delegate_to_email=None,
        )

        assert result["success"] is False
        assert "Delegate email required" in result["error"]


class TestSendBack:
    """Test send-back functionality."""

    @pytest.mark.asyncio
    async def test_send_back_to_requester(self, db_session, approval_request, approver_user):
        """Sending back from first step should send to requester."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        result = await engine.process_approval_action(
            step_id=steps[0].id,
            approver_id=approver_user.id,
            action="sent_back",
            comments="Need more info",
        )

        assert result["success"] is True
        assert result["result"] == "sent_back_to_requester"


class TestTimeout:
    """Test timeout checking."""

    @pytest.mark.asyncio
    async def test_check_timeouts_marks_expired_steps(self, db_session, approval_request, approver_user):
        """Steps past their timeout should be marked as timed out."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        # Manually set created_at to be past timeout
        steps[0].created_at = datetime.now(timezone.utc) - timedelta(hours=100)
        steps[0].timeout_hours = 48
        await db_session.flush()

        await engine.check_timeouts()

        # Refresh the step
        result = await db_session.execute(
            select(ApprovalStep).where(ApprovalStep.id == steps[0].id)
        )
        step = result.scalar_one()
        assert step.status == ApprovalStatus.TIMED_OUT
        assert step.is_active is False

    @pytest.mark.asyncio
    async def test_check_timeouts_ignores_fresh_steps(self, db_session, approval_request):
        """Fresh steps should not be timed out."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        await engine.check_timeouts()

        result = await db_session.execute(
            select(ApprovalStep).where(ApprovalStep.id == steps[0].id)
        )
        step = result.scalar_one()
        assert step.status == ApprovalStatus.PENDING


class TestPendingApprovals:
    """Test querying pending approvals for a user."""

    @pytest.mark.asyncio
    async def test_get_pending_for_approver(self, db_session, approval_request, test_user):
        """Should return pending steps for the specified approver email."""
        engine = ApprovalEngine(db_session)
        steps = await engine.create_approval_workflow(approval_request)

        # The first step is assigned to the requester's manager
        pending = await engine.get_pending_approvals_for_user("manager@company.com")
        assert len(pending) >= 1
        assert pending[0].is_active is True
        assert pending[0].status == ApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_no_pending_for_unassigned_user(self, db_session, approval_request):
        """Should return empty list for users with no pending approvals."""
        engine = ApprovalEngine(db_session)
        await engine.create_approval_workflow(approval_request)

        pending = await engine.get_pending_approvals_for_user("random@company.com")
        assert len(pending) == 0
