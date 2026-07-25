"""
Integration tests for Approvals API endpoints.
Tests pending approvals, approval actions, comments.
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.models.request import AccessRequest, RequestServer, RequestStatus, AccessType, EnvironmentType
from app.models.approval import ApprovalStep, ApprovalStatus, ApprovalType
from app.core.security import generate_request_id


@pytest_asyncio.fixture
async def approver_client(db_session: AsyncSession, approver_user: User):
    """Create a test client authenticated as an approver."""
    from app.main import app
    from app.core.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    token = create_access_token({"sub": str(approver_user.id), "email": approver_user.email})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("access_token", token)
        client.headers["X-CSRF-Token"] = "test-csrf-token"
        client.cookies.set("csrf_token", "test-csrf-token")
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def request_with_approval(db_session: AsyncSession, test_user: User, approver_user: User):
    """Create a request with an active approval step."""
    request = AccessRequest(
        request_id=generate_request_id(),
        requester_id=test_user.id,
        access_type=AccessType.USER_ACCESS,
        environment=EnvironmentType.PRODUCTION,
        purpose="Need access for deployment tasks and server maintenance",
        business_justification="Required for Q1 release deployment and ongoing operations",
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

    # Create approval step assigned to approver
    step = ApprovalStep(
        request_id=request.id,
        step_order=1,
        step_name="Cloud Team Approval",
        approval_type=ApprovalType.SEQUENTIAL,
        approver_email=approver_user.email,
        approver_role="cloud_manager",
        timeout_hours=48,
        is_active=True,
        status=ApprovalStatus.PENDING,
    )
    db_session.add(step)
    await db_session.flush()
    await db_session.refresh(request, ["servers", "approval_steps"])

    return request, step


class TestPendingApprovals:
    """Test fetching pending approvals."""

    @pytest.mark.asyncio
    async def test_get_pending_approvals(self, approver_client, request_with_approval, approver_user):
        """Should list pending approvals for the authenticated user."""
        response = await approver_client.get("/api/approvals/pending")
        assert response.status_code == 200
        data = response.json()
        assert "pending_approvals" in data
        assert "count" in data
        assert data["count"] >= 1

    @pytest.mark.asyncio
    async def test_no_pending_for_requester(self, test_client, request_with_approval, test_user):
        """Requester should see no pending approvals (not assigned to them)."""
        response = await test_client.get("/api/approvals/pending")
        if response.status_code == 200:
            data = response.json()
            assert data["count"] == 0


class TestApprovalActions:
    """Test approval action endpoints."""

    @pytest.mark.asyncio
    async def test_approve_step(self, approver_client, request_with_approval, approver_user, db_session):
        """Should approve a pending step."""
        request, step = request_with_approval

        response = await approver_client.post(
            f"/api/approvals/{step.id}/action",
            json={
                "action": "approved",
                "comments": "Looks good, approved.",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["success"] is True

    @pytest.mark.asyncio
    async def test_reject_step(self, approver_client, request_with_approval, approver_user, db_session):
        """Should reject a pending step."""
        request, step = request_with_approval

        response = await approver_client.post(
            f"/api/approvals/{step.id}/action",
            json={
                "action": "rejected",
                "comments": "Insufficient justification provided.",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["success"] is True
        assert data["result"]["result"] == "rejected"

    @pytest.mark.asyncio
    async def test_approve_nonexistent_step(self, approver_client):
        """Approving non-existent step should fail with 400."""
        response = await approver_client.post(
            "/api/approvals/99999/action",
            json={
                "action": "approved",
                "comments": "Test",
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_action_with_comments(self, approver_client, request_with_approval, db_session):
        """Should record comments with the action."""
        request, step = request_with_approval

        response = await approver_client.post(
            f"/api/approvals/{step.id}/action",
            json={
                "action": "approved",
                "comments": "Reviewed and approved for production access.",
            },
        )
        assert response.status_code == 200

        # Verify action was recorded
        from app.models.approval import ApprovalAction
        result = await db_session.execute(
            select(ApprovalAction).where(ApprovalAction.step_id == step.id)
        )
        action = result.scalar_one_or_none()
        assert action is not None
        assert action.comments == "Reviewed and approved for production access."

    @pytest.mark.asyncio
    async def test_delegate_step(self, approver_client, request_with_approval):
        """Should delegate a step to another user."""
        request, step = request_with_approval

        response = await approver_client.post(
            f"/api/approvals/{step.id}/action",
            json={
                "action": "delegated",
                "comments": "Delegating to senior engineer",
                "delegate_to_email": "senior@company.com",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["success"] is True
        assert data["result"]["result"] == "delegated"


class TestApprovalHistory:
    """Test approval history and status."""

    @pytest.mark.asyncio
    async def test_get_approval_steps_for_request(self, approver_client, request_with_approval):
        """Should be able to view approval steps for a request."""
        request, step = request_with_approval

        # Get the request details which include approval info
        response = await approver_client.get(f"/api/requests/{request.request_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending_approval"
        assert data["current_approval_step"] == 1
