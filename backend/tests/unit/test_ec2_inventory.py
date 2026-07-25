"""
Unit tests for the EC2 Inventory Service.
Tests CSV parsing, IP lookup, hostname lookup, cache behavior.
"""

import os
import csv
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.services.inventory.ec2_inventory import EC2InventoryService, EC2ServerInfo


@pytest.fixture
def ec2_csv_file():
    """Create a temporary EC2 inventory CSV file for testing."""
    tmpdir = tempfile.mkdtemp()
    csv_path = os.path.join(tmpdir, "ec2_inventory_20240101.csv")

    rows = [
        {
            "PrivateIP": "10.10.10.5",
            "PublicIP": "54.1.2.3",
            "InstanceID": "i-0123456789abcdef0",
            "AccountName": "production",
            "AccountID": "123456789012",
            "Region": "us-east-1",
            "NameTag": "web-server-01",
            "ApplicationTag": "WebApp",
            "OSTag": "Amazon Linux 2",
            "InstanceType": "t3.medium",
            "Hostname": "ip-10-10-10-5.ec2.internal",
        },
        {
            "PrivateIP": "10.20.30.40",
            "PublicIP": "",
            "InstanceID": "i-abcdef0123456789a",
            "AccountName": "development",
            "AccountID": "987654321098",
            "Region": "us-west-2",
            "NameTag": "db-server-01",
            "ApplicationTag": "Database",
            "OSTag": "Ubuntu 22.04",
            "InstanceType": "r5.large",
            "Hostname": "ip-10-20-30-40.ec2.internal",
        },
        {
            "PrivateIP": "172.16.0.100",
            "PublicIP": "3.4.5.6",
            "InstanceID": "i-1111222233334444a",
            "AccountName": "staging",
            "AccountID": "111222333444",
            "Region": "eu-west-1",
            "NameTag": "app-server-staging",
            "ApplicationTag": "StagingApp",
            "OSTag": "RHEL 8",
            "InstanceType": "m5.xlarge",
            "Hostname": "ip-172-16-0-100.ec2.internal",
        },
    ]

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    yield tmpdir

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def ec2_service(ec2_csv_file):
    """Create an EC2InventoryService with a test CSV."""
    service = EC2InventoryService()
    csv_file = Path(ec2_csv_file) / "ec2_inventory_20240101.csv"
    with patch.object(service, "_get_latest_inventory_file", return_value=csv_file):
        service._cache_by_ip.clear()
        service._cache_by_hostname.clear()
        service._cache_by_instance_id.clear()
        service._cache_loaded_at = None
        yield service


class TestEC2InventoryIPLookup:
    """Test IP address lookup."""

    def test_lookup_by_private_ip(self, ec2_service):
        """Should find server by private IP."""
        result = ec2_service.lookup_server("10.10.10.5")
        assert result is not None
        assert result.private_ip == "10.10.10.5"
        assert result.account_name == "production"
        assert result.region == "us-east-1"

    def test_lookup_by_public_ip(self, ec2_service):
        """Should find server by public IP."""
        result = ec2_service.lookup_server("54.1.2.3")
        assert result is not None
        assert result.private_ip == "10.10.10.5"
        assert result.name_tag == "web-server-01"

    def test_lookup_nonexistent_ip_returns_none(self, ec2_service):
        """Non-existent IP should return None."""
        result = ec2_service.lookup_server("99.99.99.99")
        assert result is None

    def test_lookup_server_no_public_ip(self, ec2_service):
        """Servers without public IP should still be found by private IP."""
        result = ec2_service.lookup_server("10.20.30.40")
        assert result is not None
        assert result.public_ip == ""
        assert result.account_name == "development"


class TestEC2InventoryHostnameLookup:
    """Test hostname and name tag lookup."""

    def test_lookup_by_hostname(self, ec2_service):
        """Should find server by DNS hostname."""
        result = ec2_service.lookup_server("ip-10-10-10-5.ec2.internal")
        assert result is not None
        assert result.private_ip == "10.10.10.5"

    def test_lookup_by_name_tag(self, ec2_service):
        """Should find server by name tag."""
        result = ec2_service.lookup_server("web-server-01")
        assert result is not None
        assert result.private_ip == "10.10.10.5"

    def test_hostname_lookup_case_insensitive(self, ec2_service):
        """Hostname lookup should be case-insensitive."""
        result = ec2_service.lookup_server("WEB-SERVER-01")
        assert result is not None
        assert result.private_ip == "10.10.10.5"

    def test_lookup_by_instance_id(self, ec2_service):
        """Should find server by instance ID."""
        result = ec2_service.lookup_server("i-0123456789abcdef0")
        assert result is not None
        assert result.private_ip == "10.10.10.5"


class TestEC2InventoryServerInfo:
    """Test EC2ServerInfo data class."""

    def test_server_info_all_fields(self, ec2_service):
        """All fields should be populated correctly."""
        result = ec2_service.lookup_server("172.16.0.100")
        assert result is not None
        assert result.private_ip == "172.16.0.100"
        assert result.public_ip == "3.4.5.6"
        assert result.instance_id == "i-1111222233334444a"
        assert result.account_name == "staging"
        assert result.account_id == "111222333444"
        assert result.region == "eu-west-1"
        assert result.name_tag == "app-server-staging"
        assert result.application_tag == "StagingApp"
        assert result.os_tag == "RHEL 8"
        assert result.instance_type == "m5.xlarge"

    def test_server_info_to_dict(self, ec2_service):
        """to_dict should return a dictionary with all fields."""
        result = ec2_service.lookup_server("10.10.10.5")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["private_ip"] == "10.10.10.5"
        assert d["account_name"] == "production"
        assert "hostname" in d
        assert "instance_type" in d


class TestEC2InventoryMultipleLookup:
    """Test bulk lookup functionality."""

    def test_lookup_multiple_servers(self, ec2_service):
        """Should look up multiple servers at once."""
        results = ec2_service.lookup_multiple(["10.10.10.5", "10.20.30.40", "99.99.99.99"])
        assert "10.10.10.5" in results
        assert results["10.10.10.5"] is not None
        assert results["10.10.10.5"]["account_name"] == "production"
        assert results["10.20.30.40"] is not None
        assert results["99.99.99.99"] is None


class TestEC2InventoryCache:
    """Test cache behavior."""

    def test_cache_initially_empty(self):
        """Fresh service should have empty cache."""
        service = EC2InventoryService()
        assert service._cache_by_ip == {}
        assert service._cache_loaded_at is None

    def test_should_reload_when_cache_empty(self):
        """Should reload when cache is empty."""
        service = EC2InventoryService()
        assert service._should_reload() is True

    def test_inventory_stats(self, ec2_service):
        """Stats should report correct counts after loading."""
        # Force a load
        ec2_service.lookup_server("10.10.10.5")
        stats = ec2_service.get_inventory_stats()
        assert stats["total_servers"] > 0
        assert stats["total_hostnames"] > 0
        assert stats["loaded_at"] is not None


class TestEC2InventoryAlternateFormats:
    """Test handling of alternate CSV column names."""

    def test_alternate_column_names(self):
        """Should handle alternate column naming conventions."""
        tmpdir = tempfile.mkdtemp()
        csv_path = os.path.join(tmpdir, "inventory.csv")

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Private_IP", "Public_IP", "Instance_ID", "Account_Name", "Account_ID", "Region", "Name_Tag", "Application_Tag", "OS_Tag", "Instance_Type", "Hostname"])
            writer.writerow(["10.0.0.1", "1.2.3.4", "i-alt123", "prod-alt", "999", "ap-southeast-1", "alt-server", "AltApp", "CentOS", "t2.micro", "alt-host.local"])

        service = EC2InventoryService()
        with patch.object(service, "_get_latest_inventory_file", return_value=Path(csv_path)):
            result = service.lookup_server("10.0.0.1")
            assert result is not None
            assert result.account_name == "prod-alt"
            assert result.region == "ap-southeast-1"

        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
