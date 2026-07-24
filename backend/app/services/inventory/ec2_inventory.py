"""
EC2 Inventory Service.
Reads the daily EC2 inventory export file from a shared folder and provides
lookup by IP address to return account name, region, name tag, application
name tag, OS tag, and other metadata.

Expected CSV format (flexible column mapping):
PrivateIP,PublicIP,InstanceID,AccountName,AccountID,Region,NameTag,ApplicationTag,OSTag,InstanceType,State
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from ...core.config import settings

logger = logging.getLogger(__name__)


class EC2ServerInfo:
    """Data class for EC2 server information from inventory."""

    def __init__(self, data: Dict[str, str]):
        self.private_ip = data.get("private_ip", "")
        self.public_ip = data.get("public_ip", "")
        self.instance_id = data.get("instance_id", "")
        self.account_name = data.get("account_name", "")
        self.account_id = data.get("account_id", "")
        self.region = data.get("region", "")
        self.name_tag = data.get("name_tag", "")
        self.application_tag = data.get("application_tag", "")
        self.os_tag = data.get("os_tag", "")
        self.instance_type = data.get("instance_type", "")
        self.hostname = data.get("hostname", "")

    def to_dict(self) -> Dict[str, str]:
        return {
            "private_ip": self.private_ip,
            "public_ip": self.public_ip,
            "instance_id": self.instance_id,
            "account_name": self.account_name,
            "account_id": self.account_id,
            "region": self.region,
            "name_tag": self.name_tag,
            "application_tag": self.application_tag,
            "os_tag": self.os_tag,
            "instance_type": self.instance_type,
            "hostname": self.hostname,
        }


class EC2InventoryService:
    """
    Reads daily EC2 inventory file and provides server lookup by IP or hostname.
    Caches data in memory and reloads when a newer file is detected.
    """

    def __init__(self):
        self._cache_by_ip: Dict[str, EC2ServerInfo] = {}
        self._cache_by_hostname: Dict[str, EC2ServerInfo] = {}
        self._cache_by_instance_id: Dict[str, EC2ServerInfo] = {}
        self._cache_loaded_at: Optional[datetime] = None
        self._cache_file: Optional[str] = None

    def _get_latest_inventory_file(self) -> Optional[Path]:
        """Find the latest EC2 inventory file in the shared folder."""
        inventory_path = Path(settings.EC2_INVENTORY_PATH)

        if not inventory_path.exists():
            logger.error(f"EC2 inventory path does not exist: {inventory_path}")
            return None

        if inventory_path.is_file():
            return inventory_path

        # Directory - find latest CSV
        csv_files = sorted(
            inventory_path.glob("*.csv"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        if not csv_files:
            logger.error(f"No CSV files found in EC2 inventory path: {inventory_path}")
            return None

        return csv_files[0]

    def _should_reload(self) -> bool:
        """Check if cache should be reloaded."""
        if not self._cache_by_ip:
            return True

        latest_file = self._get_latest_inventory_file()
        if not latest_file:
            return False

        if str(latest_file) != self._cache_file:
            return True

        if self._cache_loaded_at:
            elapsed = (datetime.now() - self._cache_loaded_at).total_seconds()
            if elapsed > 3600:
                return True

        return False

    def _load_cache(self) -> bool:
        """Load EC2 inventory file into memory."""
        latest_file = self._get_latest_inventory_file()
        if not latest_file:
            return False

        try:
            self._cache_by_ip.clear()
            self._cache_by_hostname.clear()
            self._cache_by_instance_id.clear()

            encoding = settings.EC2_INVENTORY_ENCODING

            with open(latest_file, "r", encoding=encoding, errors="replace") as f:
                sample = f.read(2048)
                f.seek(0)
                delimiter = ","
                if "\t" in sample and sample.count("\t") > sample.count(","):
                    delimiter = "\t"

                reader = csv.DictReader(f, delimiter=delimiter)

                for row in reader:
                    normalized = {k.strip().lower(): v.strip() if v else "" for k, v in row.items()}

                    data = {
                        "private_ip": (
                            normalized.get("privateip")
                            or normalized.get("private_ip")
                            or normalized.get("privateipaddress")
                            or ""
                        ),
                        "public_ip": (
                            normalized.get("publicip")
                            or normalized.get("public_ip")
                            or normalized.get("publicipaddress")
                            or ""
                        ),
                        "instance_id": (
                            normalized.get("instanceid")
                            or normalized.get("instance_id")
                            or ""
                        ),
                        "account_name": (
                            normalized.get("accountname")
                            or normalized.get("account_name")
                            or normalized.get("account")
                            or ""
                        ),
                        "account_id": (
                            normalized.get("accountid")
                            or normalized.get("account_id")
                            or ""
                        ),
                        "region": (
                            normalized.get("region")
                            or normalized.get("availabilityzone", "")[:-1]  # strip AZ letter
                            or ""
                        ),
                        "name_tag": (
                            normalized.get("nametag")
                            or normalized.get("name_tag")
                            or normalized.get("name")
                            or ""
                        ),
                        "application_tag": (
                            normalized.get("applicationtag")
                            or normalized.get("application_tag")
                            or normalized.get("application")
                            or normalized.get("app")
                            or ""
                        ),
                        "os_tag": (
                            normalized.get("ostag")
                            or normalized.get("os_tag")
                            or normalized.get("os")
                            or normalized.get("platform")
                            or ""
                        ),
                        "instance_type": (
                            normalized.get("instancetype")
                            or normalized.get("instance_type")
                            or ""
                        ),
                        "hostname": (
                            normalized.get("hostname")
                            or normalized.get("privatednshostname")
                            or ""
                        ),
                    }

                    server_info = EC2ServerInfo(data)

                    # Index by private IP
                    if data["private_ip"]:
                        self._cache_by_ip[data["private_ip"]] = server_info

                    # Index by public IP
                    if data["public_ip"]:
                        self._cache_by_ip[data["public_ip"]] = server_info

                    # Index by hostname / name tag
                    if data["hostname"]:
                        self._cache_by_hostname[data["hostname"].lower()] = server_info
                    if data["name_tag"]:
                        self._cache_by_hostname[data["name_tag"].lower()] = server_info

                    # Index by instance ID
                    if data["instance_id"]:
                        self._cache_by_instance_id[data["instance_id"]] = server_info

            self._cache_file = str(latest_file)
            self._cache_loaded_at = datetime.now()
            logger.info(
                f"EC2 inventory loaded: {len(self._cache_by_ip)} IPs, "
                f"{len(self._cache_by_hostname)} hostnames from {latest_file.name}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to load EC2 inventory file: {str(e)}")
            return False

    def lookup_server(self, identifier: str) -> Optional[EC2ServerInfo]:
        """
        Look up a server by IP address, hostname, or instance ID.
        Returns EC2ServerInfo with account, region, tags, etc.
        """
        if self._should_reload():
            self._load_cache()

        # Try IP lookup first
        result = self._cache_by_ip.get(identifier)
        if result:
            return result

        # Try hostname / name tag (case-insensitive)
        result = self._cache_by_hostname.get(identifier.lower())
        if result:
            return result

        # Try instance ID
        result = self._cache_by_instance_id.get(identifier)
        if result:
            return result

        return None

    def lookup_multiple(self, identifiers: List[str]) -> Dict[str, Optional[Dict[str, str]]]:
        """
        Look up multiple servers at once.
        Returns dict mapping identifier → server info dict (or None if not found).
        """
        results = {}
        for identifier in identifiers:
            info = self.lookup_server(identifier)
            results[identifier] = info.to_dict() if info else None
        return results

    def get_inventory_stats(self) -> Dict[str, Any]:
        """Get statistics about the loaded inventory."""
        if self._should_reload():
            self._load_cache()

        return {
            "total_servers": len(self._cache_by_ip),
            "total_hostnames": len(self._cache_by_hostname),
            "file": self._cache_file,
            "loaded_at": self._cache_loaded_at.isoformat() if self._cache_loaded_at else None,
        }


# Singleton instance
ec2_inventory_service = EC2InventoryService()
