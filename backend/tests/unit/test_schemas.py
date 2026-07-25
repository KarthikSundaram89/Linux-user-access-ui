"""
Unit tests for Pydantic schema validation.
Tests IP-only validation, access type validation, duplicate server detection.
"""

import pytest
from pydantic import ValidationError

from app.schemas.request import (
    ServerInput,
    AccessRequestCreate,
)


class TestServerInputValidation:
    """Test server IP address validation."""

    def test_valid_ipv4_address(self):
        """Valid IPv4 address should pass."""
        server = ServerInput(ip_address="10.10.10.5")
        assert server.ip_address == "10.10.10.5"

    def test_valid_ip_with_leading_spaces(self):
        """IP with leading/trailing spaces should be trimmed and pass."""
        server = ServerInput(ip_address="  192.168.1.1  ")
        assert server.ip_address == "192.168.1.1"

    def test_valid_ip_boundary_values(self):
        """Boundary IP addresses should pass."""
        # min
        server = ServerInput(ip_address="0.0.0.0")
        assert server.ip_address == "0.0.0.0"
        # max
        server = ServerInput(ip_address="255.255.255.255")
        assert server.ip_address == "255.255.255.255"

    def test_invalid_ip_hostname_rejected(self):
        """Hostnames should be rejected (IP-only)."""
        with pytest.raises(ValidationError) as exc_info:
            ServerInput(ip_address="server01.company.com")
        assert "not a valid IP address" in str(exc_info.value)

    def test_invalid_ip_out_of_range(self):
        """IP octet > 255 should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ServerInput(ip_address="256.1.1.1")
        assert "not a valid IP address" in str(exc_info.value)

    def test_invalid_ip_empty_string(self):
        """Empty IP should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ServerInput(ip_address="")
        assert "cannot be empty" in str(exc_info.value)

    def test_invalid_ip_incomplete(self):
        """Incomplete IP should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ServerInput(ip_address="10.10.10")
        assert "not a valid IP address" in str(exc_info.value)

    def test_invalid_ip_ipv6(self):
        """IPv6 addresses should be rejected (only IPv4 accepted)."""
        with pytest.raises(ValidationError) as exc_info:
            ServerInput(ip_address="::1")
        assert "not a valid IP address" in str(exc_info.value)

    def test_invalid_ip_with_port(self):
        """IP with port should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ServerInput(ip_address="10.10.10.5:22")
        assert "not a valid IP address" in str(exc_info.value)

    def test_invalid_ip_with_cidr(self):
        """IP with CIDR notation should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ServerInput(ip_address="10.10.10.0/24")
        assert "not a valid IP address" in str(exc_info.value)


class TestAccessRequestCreateValidation:
    """Test access request creation schema validation."""

    def _valid_request_data(self, **overrides):
        """Helper to create valid request data with optional overrides."""
        data = {
            "access_type": "user_access",
            "environment": "production",
            "purpose": "Need access for deployment tasks and server maintenance",
            "business_justification": "Required for Q1 release deployment and ongoing operations",
            "servers": [{"ip_address": "10.10.10.5"}],
        }
        data.update(overrides)
        return data

    def test_valid_request_creation(self):
        """Valid request should pass validation."""
        data = self._valid_request_data()
        request = AccessRequestCreate(**data)
        assert request.access_type == "user_access"
        assert request.environment == "production"
        assert len(request.servers) == 1

    def test_valid_access_types(self):
        """All valid access types should pass."""
        for access_type in ["user_access", "sudo_access", "both", "renew_sudo"]:
            data = self._valid_request_data(access_type=access_type)
            request = AccessRequestCreate(**data)
            assert request.access_type == access_type

    def test_invalid_access_type(self):
        """Invalid access type should be rejected."""
        data = self._valid_request_data(access_type="root_access")
        with pytest.raises(ValidationError) as exc_info:
            AccessRequestCreate(**data)
        assert "Invalid access type" in str(exc_info.value)

    def test_valid_environments(self):
        """All valid environments should pass."""
        for env in ["production", "non_production", "development", "dr", "uat"]:
            data = self._valid_request_data(environment=env)
            request = AccessRequestCreate(**data)
            assert request.environment == env

    def test_invalid_environment(self):
        """Invalid environment should be rejected."""
        data = self._valid_request_data(environment="staging")
        with pytest.raises(ValidationError) as exc_info:
            AccessRequestCreate(**data)
        assert "Invalid environment" in str(exc_info.value)

    def test_duplicate_server_ips_rejected(self):
        """Duplicate server IPs should be rejected."""
        data = self._valid_request_data(
            servers=[
                {"ip_address": "10.10.10.5"},
                {"ip_address": "10.10.10.5"},
            ]
        )
        with pytest.raises(ValidationError) as exc_info:
            AccessRequestCreate(**data)
        assert "Duplicate server IP" in str(exc_info.value)

    def test_multiple_unique_servers_accepted(self):
        """Multiple unique server IPs should pass."""
        data = self._valid_request_data(
            servers=[
                {"ip_address": "10.10.10.5"},
                {"ip_address": "10.10.10.6"},
                {"ip_address": "192.168.1.100"},
            ]
        )
        request = AccessRequestCreate(**data)
        assert len(request.servers) == 3

    def test_empty_servers_rejected(self):
        """At least one server is required."""
        data = self._valid_request_data(servers=[])
        with pytest.raises(ValidationError):
            AccessRequestCreate(**data)

    def test_purpose_too_short(self):
        """Purpose shorter than 10 chars should be rejected."""
        data = self._valid_request_data(purpose="short")
        with pytest.raises(ValidationError):
            AccessRequestCreate(**data)

    def test_business_justification_too_short(self):
        """Business justification shorter than 10 chars should be rejected."""
        data = self._valid_request_data(business_justification="short")
        with pytest.raises(ValidationError):
            AccessRequestCreate(**data)

    def test_optional_fields(self):
        """Optional fields (application_name, project_name) default to None."""
        data = self._valid_request_data()
        request = AccessRequestCreate(**data)
        assert request.application_name is None
        assert request.project_name is None

    def test_is_renewal_default_false(self):
        """is_renewal should default to False."""
        data = self._valid_request_data()
        request = AccessRequestCreate(**data)
        assert request.is_renewal is False
