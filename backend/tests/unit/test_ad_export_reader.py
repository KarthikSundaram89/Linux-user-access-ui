"""
Unit tests for the AD Export Reader service.
Tests CSV parsing, user lookup by email, cache reload behavior.
"""

import os
import csv
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.services.auth.ad_export_reader import ADExportReader


@pytest.fixture
def ad_csv_file():
    """Create a temporary AD export CSV file for testing."""
    tmpdir = tempfile.mkdtemp()
    csv_path = os.path.join(tmpdir, "ad_export_20240101.csv")

    rows = [
        {
            "Email": "karthikeyan.sundaram@company.com",
            "DisplayName": "Karthikeyan Sundaram",
            "Department": "Engineering",
            "JobTitle": "Senior Developer",
            "EmployeeID": "EMP001",
            "ManagerEmail": "manager@company.com",
            "ManagerName": "Team Manager",
            "SAMAccountName": "karthikeyan.sundaram",
        },
        {
            "Email": "john.doe@company.com",
            "DisplayName": "John Doe",
            "Department": "DevOps",
            "JobTitle": "Cloud Engineer",
            "EmployeeID": "EMP002",
            "ManagerEmail": "manager2@company.com",
            "ManagerName": "Another Manager",
            "SAMAccountName": "john.doe",
        },
        {
            "Email": "JANE.Smith@Company.COM",
            "DisplayName": "Jane Smith",
            "Department": "Security",
            "JobTitle": "InfoSec Analyst",
            "EmployeeID": "EMP003",
            "ManagerEmail": "secmgr@company.com",
            "ManagerName": "Security Manager",
            "SAMAccountName": "jane.smith",
        },
    ]

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    yield tmpdir

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def ad_reader(ad_csv_file):
    """Create an ADExportReader instance with a test CSV path."""
    reader = ADExportReader()
    with patch.object(reader, "_get_latest_export_file", return_value=Path(ad_csv_file) / "ad_export_20240101.csv"):
        # Force reload on first access
        reader._cache.clear()
        reader._cache_loaded_at = None
        yield reader


class TestADExportReaderParsing:
    """Test CSV parsing and data normalization."""

    def test_load_cache_populates_users(self, ad_reader):
        """Loading cache should populate all users from CSV."""
        user = ad_reader.get_user_by_email("karthikeyan.sundaram@company.com")
        assert user is not None
        assert user["display_name"] == "Karthikeyan Sundaram"
        assert user["department"] == "Engineering"

    def test_case_insensitive_email_lookup(self, ad_reader):
        """Email lookup should be case-insensitive."""
        user = ad_reader.get_user_by_email("JANE.Smith@Company.COM")
        assert user is not None
        assert user["display_name"] == "Jane Smith"

        # Also works with lowercase
        user2 = ad_reader.get_user_by_email("jane.smith@company.com")
        assert user2 is not None
        assert user2["display_name"] == "Jane Smith"

    def test_user_fields_populated(self, ad_reader):
        """All expected fields should be populated."""
        user = ad_reader.get_user_by_email("john.doe@company.com")
        assert user is not None
        assert user["email"] == "john.doe@company.com"
        assert user["display_name"] == "John Doe"
        assert user["department"] == "DevOps"
        assert user["job_title"] == "Cloud Engineer"
        assert user["employee_id"] == "EMP002"
        assert user["manager_email"] == "manager2@company.com"
        assert user["manager_name"] == "Another Manager"
        assert user["sam_account_name"] == "john.doe"

    def test_user_not_found_returns_none(self, ad_reader):
        """Non-existent user should return None."""
        user = ad_reader.get_user_by_email("nonexistent@company.com")
        assert user is None


class TestADExportReaderLookup:
    """Test various lookup methods."""

    def test_lookup_by_sam_account(self, ad_reader):
        """Should find user by SAM account name."""
        user = ad_reader.get_user_by_sam_account("karthikeyan.sundaram")
        assert user is not None
        assert user["email"] == "karthikeyan.sundaram@company.com"

    def test_lookup_by_sam_account_case_insensitive(self, ad_reader):
        """SAM account lookup should be case-insensitive."""
        user = ad_reader.get_user_by_sam_account("JOHN.DOE")
        assert user is not None
        assert user["email"] == "john.doe@company.com"

    def test_search_users_by_name(self, ad_reader):
        """Should find users by partial name search."""
        results = ad_reader.search_users("karthikeyan")
        assert len(results) >= 1
        assert results[0]["display_name"] == "Karthikeyan Sundaram"

    def test_search_users_by_email(self, ad_reader):
        """Should find users by partial email search."""
        results = ad_reader.search_users("john.doe")
        assert len(results) >= 1
        assert results[0]["email"] == "john.doe@company.com"

    def test_search_users_limit(self, ad_reader):
        """Search results should respect the limit parameter."""
        results = ad_reader.search_users("company", limit=2)
        assert len(results) <= 2

    def test_get_total_employees(self, ad_reader):
        """Should return the total number of employees."""
        total = ad_reader.get_total_employees()
        assert total == 3


class TestADExportReaderCache:
    """Test cache reload behavior."""

    def test_cache_initially_empty(self):
        """A fresh reader should have an empty cache."""
        reader = ADExportReader()
        assert reader._cache == {}
        assert reader._cache_loaded_at is None

    def test_should_reload_when_cache_empty(self):
        """Should reload when cache is empty."""
        reader = ADExportReader()
        assert reader._should_reload() is True

    def test_should_not_reload_when_cache_fresh(self, ad_reader):
        """Should not reload when cache was recently loaded."""
        # Force a load
        ad_reader.get_user_by_email("john.doe@company.com")
        # Now it should not need reload
        assert ad_reader._should_reload() is False


class TestADExportReaderAlternateFormats:
    """Test handling of alternate CSV column names."""

    def test_alternate_column_names(self):
        """Reader should handle alternate column naming conventions."""
        tmpdir = tempfile.mkdtemp()
        csv_path = os.path.join(tmpdir, "ad_export.csv")

        # Use alternate column names
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Mail", "Name", "Dept", "Title", "EmpID", "Manager", "ManagerDisplayName", "Username"])
            writer.writerow(["alt.user@test.com", "Alt User", "IT", "Analyst", "A001", "mgr@test.com", "The Manager", "alt.user"])

        reader = ADExportReader()
        with patch.object(reader, "_get_latest_export_file", return_value=Path(csv_path)):
            user = reader.get_user_by_email("alt.user@test.com")
            assert user is not None
            assert user["display_name"] == "Alt User"

        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_tab_delimited_file(self):
        """Reader should handle tab-delimited files."""
        tmpdir = tempfile.mkdtemp()
        csv_path = os.path.join(tmpdir, "ad_export.csv")

        with open(csv_path, "w") as f:
            f.write("Email\tDisplayName\tDepartment\tJobTitle\tEmployeeID\tManagerEmail\tManagerName\tSAMAccountName\n")
            f.write("tab.user@test.com\tTab User\tFinance\tAccountant\tT001\tmgr@test.com\tManager\ttab.user\n")

        reader = ADExportReader()
        with patch.object(reader, "_get_latest_export_file", return_value=Path(csv_path)):
            user = reader.get_user_by_email("tab.user@test.com")
            assert user is not None
            assert user["display_name"] == "Tab User"
            assert user["department"] == "Finance"

        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
