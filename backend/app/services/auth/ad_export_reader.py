"""
AD Export File Reader Service.
Reads employee details from the latest daily Active Directory export file
stored in a shared folder. Replaces Microsoft Graph API for user profile data.

Expected CSV format (configurable columns):
EmployeeID,Email,DisplayName,Department,JobTitle,ManagerEmail,ManagerName,SAMAccountName
"""

import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from ...core.config import settings

logger = logging.getLogger(__name__)


class ADExportReader:
    """
    Reads and caches employee data from the latest daily AD export file.
    The file is expected to be a CSV placed daily in a shared folder.
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_loaded_at: Optional[datetime] = None
        self._cache_file: Optional[str] = None

    def _get_latest_export_file(self) -> Optional[Path]:
        """
        Find the latest AD export file in the shared folder.
        Supports patterns like:
          - ad_export_YYYYMMDD.csv
          - ad_export_latest.csv
          - *.csv (picks most recently modified)
        """
        export_path = Path(settings.AD_EXPORT_PATH)

        if not export_path.exists():
            logger.error(f"AD export path does not exist: {export_path}")
            return None

        if export_path.is_file():
            # Direct file path configured
            return export_path

        # Directory - find latest CSV file
        csv_files = sorted(
            export_path.glob("*.csv"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        if not csv_files:
            logger.error(f"No CSV files found in AD export path: {export_path}")
            return None

        return csv_files[0]

    def _should_reload(self) -> bool:
        """Check if cache should be reloaded (new file or stale cache)."""
        if not self._cache:
            return True

        latest_file = self._get_latest_export_file()
        if not latest_file:
            return False

        # Reload if different file or cache is older than 1 hour
        if str(latest_file) != self._cache_file:
            return True

        if self._cache_loaded_at:
            elapsed = (datetime.now() - self._cache_loaded_at).total_seconds()
            if elapsed > 3600:  # Reload every hour
                return True

        return False

    def _load_cache(self) -> bool:
        """Load AD export file into memory cache."""
        latest_file = self._get_latest_export_file()
        if not latest_file:
            return False

        try:
            self._cache.clear()
            encoding = settings.AD_EXPORT_ENCODING

            with open(latest_file, "r", encoding=encoding, errors="replace") as f:
                # Detect delimiter
                sample = f.read(2048)
                f.seek(0)
                delimiter = ","
                if "\t" in sample and sample.count("\t") > sample.count(","):
                    delimiter = "\t"

                reader = csv.DictReader(f, delimiter=delimiter)

                # Normalize field names (case-insensitive, strip spaces)
                for row in reader:
                    normalized = {k.strip().lower(): v.strip() if v else "" for k, v in row.items()}

                    email = (
                        normalized.get("email")
                        or normalized.get("emailaddress")
                        or normalized.get("mail")
                        or normalized.get("userprincipalname")
                        or ""
                    ).lower()

                    if not email:
                        continue

                    self._cache[email] = {
                        "email": email,
                        "display_name": (
                            normalized.get("displayname")
                            or normalized.get("display_name")
                            or normalized.get("name")
                            or normalized.get("fullname")
                            or ""
                        ),
                        "department": (
                            normalized.get("department")
                            or normalized.get("dept")
                            or ""
                        ),
                        "job_title": (
                            normalized.get("jobtitle")
                            or normalized.get("job_title")
                            or normalized.get("title")
                            or ""
                        ),
                        "employee_id": (
                            normalized.get("employeeid")
                            or normalized.get("employee_id")
                            or normalized.get("empid")
                            or ""
                        ),
                        "manager_email": (
                            normalized.get("manageremail")
                            or normalized.get("manager_email")
                            or normalized.get("manager")
                            or ""
                        ).lower(),
                        "manager_name": (
                            normalized.get("managername")
                            or normalized.get("manager_name")
                            or normalized.get("managerdisplayname")
                            or ""
                        ),
                        "sam_account_name": (
                            normalized.get("samaccountname")
                            or normalized.get("sam_account_name")
                            or normalized.get("username")
                            or ""
                        ),
                    }

            self._cache_file = str(latest_file)
            self._cache_loaded_at = datetime.now()
            logger.info(
                f"AD export loaded: {len(self._cache)} employees from {latest_file.name}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to load AD export file: {str(e)}")
            return False

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Look up an employee by email address.
        Returns dict with display_name, department, job_title, etc.
        """
        if self._should_reload():
            self._load_cache()

        return self._cache.get(email.lower())

    def get_user_by_sam_account(self, sam_account: str) -> Optional[Dict[str, Any]]:
        """Look up an employee by SAM account name."""
        if self._should_reload():
            self._load_cache()

        sam_lower = sam_account.lower()
        for user_data in self._cache.values():
            if user_data.get("sam_account_name", "").lower() == sam_lower:
                return user_data
        return None

    def search_users(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search users by name or email (for autocomplete/lookup)."""
        if self._should_reload():
            self._load_cache()

        query_lower = query.lower()
        results = []
        for user_data in self._cache.values():
            if (
                query_lower in user_data.get("email", "")
                or query_lower in user_data.get("display_name", "").lower()
                or query_lower in user_data.get("employee_id", "").lower()
            ):
                results.append(user_data)
                if len(results) >= limit:
                    break
        return results

    def get_total_employees(self) -> int:
        """Get count of employees in the export."""
        if self._should_reload():
            self._load_cache()
        return len(self._cache)


# Singleton instance
ad_export_reader = ADExportReader()
