"""
Integration tests for Access Requests API endpoints.
Tests CRUD, draft, clone, retry, CSV upload.
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.models.request import AccessRequest, RequestServer, RequestStatus, AccessType, EnvironmentType
from app.core.security import generate_request_id


class TestCreateRequest:
    """Test request creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_request_success(self, test_client, test_user):
        """Valid request should be created successfully."""
        response = await test_client.post(
            "/api/requests/",
            json={
                "access_type": "user_access",
                "environment": "production",
                "purpose": "Need access for deployment tasks and server maintenance",
                "business_justification": "Required for Q1 release deployment and ongoing operations",
                "servers": [{"ip_address": "10.10.10.5"}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["access_type"] == "user_access"
        assert data["environment"] == "production"
        assert data["status"] == "pending_approval"
        assert data["request_id"].startswith("LAR-")
        assert len(data["servers"]) == 1
        assert data["servers"][0]["ip_address"] == "10.10.10.5"

    @pytest.mark.asyncio
    async def test_create_request_multiple_servers(self, test_client, test_user):
        """Request with multiple servers should be created."""
        response = await test_client.post(
            "/api/requests/",
            json={
                "access_type": "both",
                "environment": "non_production",
                "purpose": "Need access for development and testing activities",
                "business_justification": "Ongoing feature development requires server access",
                "servers": [
                    {"ip_address": "10.10.10.5"},
                    {"ip_address": "10.10.10.6"},
                    {"ip_address": "192.168.1.100"},
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["servers"]) == 3

    @pytest.mark.asyncio
    async def test_create_request_invalid_ip_rejected(self, test_client, test_user):
        """Invalid IP address should be rejected."""
        response = await test_client.post(
            "/api/requests/",
            json={
                "access_type": "user_access",
                "environment": "production",
                "purpose": "Need access for deployment tasks and server maintenance",
                "business_justification": "Required for Q1 release deployment and ongoing operations",
                "servers": [{"ip_address": "not-an-ip"}],
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_request_duplicate_ips_rejected(self, test_client, test_user):
        """Duplicate server IPs should be rejected."""
        response = await test_client.post(
            "/api/requests/",
            json={
                "access_type": "user_access",
                "environment": "production",
                "purpose": "Need access for deployment tasks and server maintenance",
                "business_justification": "Required for Q1 release deployment and ongoing operations",
                "servers": [
                    {"ip_address": "10.10.10.5"},
                    {"ip_address": "10.10.10.5"},
                ],
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_request_invalid_access_type(self, test_client, test_user):
        """Invalid access type should be rejected."""
        response = await test_client.post(
            "/api/requests/",
            json={
                "access_type": "root_shell",
                "environment": "production",
                "purpose": "Need access for deployment tasks and server maintenance",
                "business_justification": "Required for Q1 release deployment and ongoing operations",
                "servers": [{"ip_address": "10.10.10.5"}],
            },
        )
        assert response.status_code == 422


class TestListRequests:
    """Test request listing endpoint."""

    @pytest.mark.asyncio
    async def test_list_requests_empty(self, test_client, test_user):
        """Empty request list should return properly."""
        response = await test_client.get("/api/requests/")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    @pytest.mark.asyncio
    async def test_list_requests_after_creation(self, test_client, test_user):
        """Should list requests after creation."""
        # Create a request first
        await test_client.post(
            "/api/requests/",
            json={
                "access_type": "user_access",
                "environment": "development",
                "purpose": "Need access for development tasks and testing work",
                "business_justification": "Required for sprint development activities",
                "servers": [{"ip_address": "10.10.10.5"}],
            },
        )

        response = await test_client.get("/api/requests/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1


class TestGetRequest:
    """Test getting a specific request."""

    @pytest.mark.asyncio
    async def test_get_request_by_id(self, test_client, test_user, sample_request):
        """Should retrieve a specific request by ID."""
        response = await test_client.get(f"/api/requests/{sample_request.request_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == sample_request.request_id
        assert data["access_type"] == "user_access"

    @pytest.mark.asyncio
    async def test_get_nonexistent_request(self, test_client, test_user):
        """Non-existent request should return 404."""
        response = await test_client.get("/api/requests/LAR-99999999-XXXXXXXX")
        assert response.status_code == 404


class TestCancelRequest:
    """Test request cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_pending_request(self, test_client, test_user, sample_request):
        """Should cancel a pending request."""
        response = await test_client.post(f"/api/requests/{sample_request.request_id}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Request cancelled"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_request(self, test_client, test_user):
        """Cancelling non-existent request should return 404."""
        response = await test_client.post("/api/requests/LAR-99999999-XXXXXXXX/cancel")
        assert response.status_code == 404


class TestDraftRequest:
    """Test draft save and submit."""

    @pytest.mark.asyncio
    async def test_save_draft(self, test_client, test_user):
        """Should save a request as draft."""
        response = await test_client.post(
            "/api/requests/draft",
            json={
                "access_type": "sudo_access",
                "environment": "uat",
                "purpose": "Need sudo access for system configuration tasks",
                "business_justification": "Required for UAT environment setup and testing",
                "servers": [{"ip_address": "10.0.0.1"}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "draft"
        assert data["request_id"].startswith("LAR-")

    @pytest.mark.asyncio
    async def test_submit_draft(self, test_client, test_user, db_session):
        """Should submit a draft request for approval."""
        # Save draft first
        response = await test_client.post(
            "/api/requests/draft",
            json={
                "access_type": "user_access",
                "environment": "development",
                "purpose": "Need access for development tasks and testing work",
                "business_justification": "Required for sprint development activities",
                "servers": [{"ip_address": "10.0.0.1"}],
            },
        )
        assert response.status_code == 200
        draft_id = response.json()["request_id"]

        # Submit the draft
        response = await test_client.post(f"/api/requests/{draft_id}/submit")
        assert response.status_code == 200
        data = response.json()
        assert "submitted for approval" in data["message"]


class TestCloneRequest:
    """Test request cloning."""

    @pytest.mark.asyncio
    async def test_clone_request(self, test_client, test_user, sample_request):
        """Should clone an existing request as a draft."""
        response = await test_client.post(f"/api/requests/{sample_request.request_id}/clone")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "draft"
        assert data["request_id"] != sample_request.request_id
        assert data["access_type"] == "user_access"
        assert data["environment"] == "production"

    @pytest.mark.asyncio
    async def test_clone_nonexistent_request(self, test_client, test_user):
        """Cloning non-existent request should return 404."""
        response = await test_client.post("/api/requests/LAR-99999999-XXXXXXXX/clone")
        assert response.status_code == 404


class TestCSVUpload:
    """Test CSV file upload for bulk server input."""

    @pytest.mark.asyncio
    async def test_upload_valid_csv(self, test_client, test_user):
        """Should parse valid IPs from CSV."""
        csv_content = "ip_address\n10.10.10.5\n10.10.10.6\n192.168.1.100\n"

        response = await test_client.post(
            "/api/requests/upload-csv",
            files={"file": ("servers.csv", csv_content.encode(), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_valid"] == 3
        assert "10.10.10.5" in data["valid_ips"]
        assert "10.10.10.6" in data["valid_ips"]
        assert "192.168.1.100" in data["valid_ips"]

    @pytest.mark.asyncio
    async def test_upload_csv_with_invalid_ips(self, test_client, test_user):
        """Should report invalid IPs separately."""
        csv_content = "ip\n10.10.10.5\nnot-an-ip\n256.1.1.1\n10.10.10.6\n"

        response = await test_client.post(
            "/api/requests/upload-csv",
            files={"file": ("servers.csv", csv_content.encode(), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_valid"] == 2
        assert len(data["invalid"]) == 2

    @pytest.mark.asyncio
    async def test_upload_csv_detects_duplicates(self, test_client, test_user):
        """Should detect and report duplicate IPs."""
        csv_content = "10.10.10.5\n10.10.10.5\n10.10.10.6\n"

        response = await test_client.post(
            "/api/requests/upload-csv",
            files={"file": ("servers.csv", csv_content.encode(), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_valid"] == 2
        assert "10.10.10.5" in data["duplicates"]

    @pytest.mark.asyncio
    async def test_upload_csv_plain_ips(self, test_client, test_user):
        """Should handle plain IP list (no header)."""
        csv_content = "10.0.0.1\n10.0.0.2\n10.0.0.3\n"

        response = await test_client.post(
            "/api/requests/upload-csv",
            files={"file": ("servers.txt", csv_content.encode(), "text/plain")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_valid"] == 3

    @pytest.mark.asyncio
    async def test_upload_csv_too_large(self, test_client, test_user):
        """File exceeding size limit should be rejected."""
        # Create content > 1MB
        large_content = "10.10.10.5\n" * 200000  # ~2MB

        response = await test_client.post(
            "/api/requests/upload-csv",
            files={"file": ("large.csv", large_content.encode(), "text/csv")},
        )
        assert response.status_code == 413


class TestRetryRequest:
    """Test retry endpoint for failed provisioning."""

    @pytest.mark.asyncio
    async def test_retry_non_failed_request_rejected(self, test_client, test_user, sample_request):
        """Cannot retry a request that is not in failed state."""
        response = await test_client.post(f"/api/requests/{sample_request.request_id}/retry")
        assert response.status_code == 400
        assert "failed servers" in response.json()["detail"]
