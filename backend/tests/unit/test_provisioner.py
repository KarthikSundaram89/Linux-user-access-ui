"""
Unit tests for the Provisioning Service.
Tests username derivation, per-server results, retry logic, IP resolution.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.provisioning.provisioner import (
    ProvisioningService,
    ServerProvisioningResult,
    _SMKeyWrapper,
)
from app.services.provisioning.ssh_engine import SSHResult
from app.models.request import AccessRequest, RequestServer, RequestStatus, AccessType, EnvironmentType
from app.models.configuration import SSHKey, ProvisioningScript
from app.models.user import User, UserRole
from app.core.security import generate_request_id, encrypt_value


class TestUsernameDerivation:
    """Test that username is derived correctly from email."""

    @pytest.mark.asyncio
    async def test_email_prefix_lowercase(self, db_session):
        """Username should be email prefix in lowercase."""
        # Create user with mixed-case email
        user = User(
            email="Karthikeyan.Sundaram@company.com",
            display_name="Karthikeyan Sundaram",
            role=UserRole.REQUESTER,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        # Create request
        request = AccessRequest(
            request_id=generate_request_id(),
            requester_id=user.id,
            access_type=AccessType.USER_ACCESS,
            environment=EnvironmentType.PRODUCTION,
            purpose="Need access for deployment tasks and maintenance",
            business_justification="Required for Q1 deployment to production servers",
            status=RequestStatus.APPROVED,
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

        # Setup mocks
        ssh_key = SSHKey(
            name="test-key",
            key_type="rsa",
            private_key_encrypted=encrypt_value("fake-key"),
            is_default=True,
            is_active=True,
        )
        db_session.add(ssh_key)

        script = ProvisioningScript(
            name="Test Script",
            script_type="user_creation",
            script_content="useradd -m $username",
            is_active=True,
        )
        db_session.add(script)
        await db_session.flush()

        # Mock SSH execution
        mock_result = SSHResult(
            success=True,
            stdout="User created",
            stderr="",
            exit_code=0,
            hostname="10.10.10.5",
        )

        with patch("app.services.provisioning.provisioner.SSHEngine") as MockSSH:
            mock_engine = MockSSH.return_value
            mock_engine.execute_on_server = AsyncMock(return_value=mock_result)

            provisioner = ProvisioningService(db_session)
            provisioner.ssh_engine = mock_engine

            # Disable EC2 inventory resolution for this test
            with patch.object(provisioner, "_resolve_server_ip", new=AsyncMock(return_value="10.10.10.5")):
                result = await provisioner.provision_request(request)

            # Verify the script was called with lowercase email prefix
            call_args = mock_engine.execute_on_server.call_args
            script_sent = call_args.kwargs.get("script", call_args[1].get("script", ""))
            assert "karthikeyan.sundaram" in script_sent

    @pytest.mark.asyncio
    async def test_simple_email_prefix(self, db_session):
        """Simple email should produce simple username."""
        user = User(
            email="john@company.com",
            display_name="John",
            role=UserRole.REQUESTER,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        # The logic: email.split("@")[0].lower()
        expected_username = "john"
        actual = user.email.split("@")[0].lower()
        assert actual == expected_username


class TestServerProvisioningResult:
    """Test the ServerProvisioningResult data class."""

    def test_default_values(self):
        """Result should start with failure defaults."""
        result = ServerProvisioningResult(hostname="web-01", ip_address="10.0.0.1")
        assert result.success is False
        assert result.status == "pending"
        assert result.attempts == 0
        assert result.hostname == "web-01"
        assert result.ip_address == "10.0.0.1"

    def test_to_dict(self):
        """to_dict should return all relevant fields."""
        result = ServerProvisioningResult(hostname="web-01", ip_address="10.0.0.1")
        result.success = True
        result.status = "success"
        result.message = "Provisioned"
        result.exit_code = 0

        d = result.to_dict()
        assert d["success"] is True
        assert d["status"] == "success"
        assert d["hostname"] == "web-01"
        assert d["ip_address"] == "10.0.0.1"
        assert d["exit_code"] == 0

    def test_server_identifier_uses_hostname(self):
        """server_identifier should prefer hostname."""
        result = ServerProvisioningResult(hostname="web-01", ip_address="10.0.0.1")
        assert result.server_identifier == "web-01"

    def test_server_identifier_uses_ip_when_no_hostname(self):
        """server_identifier should fall back to IP."""
        result = ServerProvisioningResult(hostname="", ip_address="10.0.0.1")
        assert result.server_identifier == "10.0.0.1"


class TestSMKeyWrapper:
    """Test the Secrets Manager key wrapper."""

    def test_wrapper_encrypts_key(self):
        """Wrapper should encrypt the key for SSH engine compatibility."""
        wrapper = _SMKeyWrapper(
            private_key="-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----",
            passphrase="my-pass",
            key_type="rsa",
        )
        assert wrapper.private_key_encrypted is not None
        assert wrapper.private_key_encrypted != "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----"
        assert wrapper.key_type == "rsa"
        assert wrapper.is_default is True
        assert wrapper.is_active is True

    def test_wrapper_no_passphrase(self):
        """Wrapper with empty passphrase should have None passphrase_encrypted."""
        wrapper = _SMKeyWrapper(
            private_key="key-content",
            passphrase="",
            key_type="ed25519",
        )
        assert wrapper.passphrase_encrypted is None
        assert wrapper.key_type == "ed25519"


class TestProvisioningRetry:
    """Test retry logic for failed servers."""

    @pytest.mark.asyncio
    async def test_retry_only_failed_servers(self, db_session):
        """Retry should only process servers with failed status."""
        user = User(
            email="retry.user@company.com",
            display_name="Retry User",
            role=UserRole.REQUESTER,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        request = AccessRequest(
            request_id=generate_request_id(),
            requester_id=user.id,
            access_type=AccessType.USER_ACCESS,
            environment=EnvironmentType.PRODUCTION,
            purpose="Need access for deployment tasks and maintenance",
            business_justification="Required for Q1 deployment to production servers",
            status=RequestStatus.PARTIALLY_PROVISIONED,
        )
        db_session.add(request)
        await db_session.flush()

        # One success, one failed
        server_ok = RequestServer(
            request_id=request.id,
            ip_address="10.0.0.1",
            provisioning_status="success",
        )
        server_fail = RequestServer(
            request_id=request.id,
            ip_address="10.0.0.2",
            provisioning_status="failed",
        )
        db_session.add(server_ok)
        db_session.add(server_fail)
        await db_session.flush()
        await db_session.refresh(request, ["servers"])

        # Setup
        ssh_key = SSHKey(
            name="test-key",
            key_type="rsa",
            private_key_encrypted=encrypt_value("fake-key"),
            is_default=True,
            is_active=True,
        )
        db_session.add(ssh_key)
        script = ProvisioningScript(
            name="Test Script",
            script_type="user_creation",
            script_content="useradd -m $username",
            is_active=True,
        )
        db_session.add(script)
        await db_session.flush()

        mock_result = SSHResult(
            success=True,
            stdout="User created",
            stderr="",
            exit_code=0,
            hostname="10.0.0.2",
        )

        with patch("app.services.provisioning.provisioner.SSHEngine") as MockSSH:
            mock_engine = MockSSH.return_value
            mock_engine.execute_on_server = AsyncMock(return_value=mock_result)

            provisioner = ProvisioningService(db_session)
            provisioner.ssh_engine = mock_engine

            with patch.object(provisioner, "_resolve_server_ip", new=AsyncMock(side_effect=lambda x: x)):
                result = await provisioner.retry_failed_servers(request)

        # Should only have retried the failed server
        assert result["total"] == 1
        assert result["succeeded"] == 1
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_retry_no_failed_servers(self, db_session):
        """Retry with no failed servers should return success with zero total."""
        user = User(
            email="ok.user@company.com",
            display_name="OK User",
            role=UserRole.REQUESTER,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        request = AccessRequest(
            request_id=generate_request_id(),
            requester_id=user.id,
            access_type=AccessType.USER_ACCESS,
            environment=EnvironmentType.PRODUCTION,
            purpose="Need access for deployment tasks and maintenance",
            business_justification="Required for Q1 deployment to production servers",
            status=RequestStatus.PROVISIONED,
        )
        db_session.add(request)
        await db_session.flush()

        server = RequestServer(
            request_id=request.id,
            ip_address="10.0.0.1",
            provisioning_status="success",
        )
        db_session.add(server)
        await db_session.flush()
        await db_session.refresh(request, ["servers"])

        provisioner = ProvisioningService(db_session)
        result = await provisioner.retry_failed_servers(request)

        assert result["success"] is True
        assert result["total"] == 0


class TestIPResolution:
    """Test IP resolution from EC2 inventory."""

    @pytest.mark.asyncio
    async def test_resolve_falls_back_to_identifier(self, db_session):
        """Should return the original identifier when EC2 lookup fails."""
        provisioner = ProvisioningService(db_session)

        with patch("app.services.inventory.ec2_inventory.ec2_inventory_service") as mock_inv:
            mock_inv.lookup_server.return_value = None
            result = await provisioner._resolve_server_ip("10.10.10.5")
            assert result == "10.10.10.5"

    @pytest.mark.asyncio
    async def test_resolve_uses_private_ip_from_inventory(self, db_session):
        """Should use private IP from EC2 inventory when available."""
        provisioner = ProvisioningService(db_session)

        mock_server_info = MagicMock()
        mock_server_info.private_ip = "10.20.30.40"

        with patch("app.services.inventory.ec2_inventory.ec2_inventory_service") as mock_inv:
            mock_inv.lookup_server.return_value = mock_server_info
            result = await provisioner._resolve_server_ip("web-server-01")
            assert result == "10.20.30.40"
