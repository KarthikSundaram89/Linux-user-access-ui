"""
AWS EC2 Live Status Service.
Makes AWS API calls to get the current instance state (running, stopped, etc.)
using the account name from the EC2 inventory file to determine which
AWS profile or credentials to use.
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound

from ...core.config import settings

logger = logging.getLogger(__name__)


class AWSEC2StatusService:
    """
    Calls AWS DescribeInstances API to get live EC2 instance status.
    Uses the account_name from the inventory file to select the correct
    AWS CLI profile (configured in ~/.aws/credentials or via assume-role).
    """

    def __init__(self):
        self._session_cache: Dict[str, boto3.Session] = {}

    def _get_session(self, account_name: str, region: str) -> boto3.Session:
        """
        Get or create a boto3 session for a given account.
        Uses the AWS_PROFILE_MAPPING config to map account names to AWS profiles.
        """
        cache_key = f"{account_name}:{region}"
        if cache_key in self._session_cache:
            return self._session_cache[cache_key]

        profile_map = settings.aws_profile_map
        profile_name = profile_map.get(account_name)

        try:
            if profile_name:
                session = boto3.Session(profile_name=profile_name, region_name=region)
            else:
                # Try using account_name directly as profile name
                try:
                    session = boto3.Session(profile_name=account_name, region_name=region)
                except ProfileNotFound:
                    # Fall back to default credentials
                    session = boto3.Session(region_name=region)

            self._session_cache[cache_key] = session
            return session

        except Exception as e:
            logger.warning(f"Failed to create session for account '{account_name}': {e}")
            # Fallback to default session
            session = boto3.Session(region_name=region)
            self._session_cache[cache_key] = session
            return session

    async def get_instance_status(
        self,
        instance_id: str,
        account_name: str,
        region: str,
    ) -> Dict[str, Any]:
        """
        Get the current status of a single EC2 instance.
        Returns dict with state, state_reason, launch_time, etc.
        """
        try:
            result = await asyncio.to_thread(
                self._describe_instance, instance_id, account_name, region
            )
            return result
        except Exception as e:
            logger.error(f"Failed to get status for {instance_id}: {str(e)}")
            return {
                "instance_id": instance_id,
                "state": "unknown",
                "error": str(e),
            }

    def _describe_instance(
        self, instance_id: str, account_name: str, region: str
    ) -> Dict[str, Any]:
        """Synchronous AWS API call (run in thread pool)."""
        session = self._get_session(account_name, region or settings.AWS_DEFAULT_REGION)
        ec2_client = session.client("ec2")

        try:
            response = ec2_client.describe_instances(InstanceIds=[instance_id])
            reservations = response.get("Reservations", [])

            if not reservations:
                return {
                    "instance_id": instance_id,
                    "state": "not_found",
                    "error": "Instance not found in AWS",
                }

            instance = reservations[0]["Instances"][0]
            state = instance.get("State", {}).get("Name", "unknown")
            launch_time = instance.get("LaunchTime")

            return {
                "instance_id": instance_id,
                "state": state,
                "instance_type": instance.get("InstanceType", ""),
                "launch_time": launch_time.isoformat() if launch_time else None,
                "private_ip": instance.get("PrivateIpAddress", ""),
                "public_ip": instance.get("PublicIpAddress", ""),
                "error": None,
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "InvalidInstanceID.NotFound":
                return {
                    "instance_id": instance_id,
                    "state": "not_found",
                    "error": "Instance not found",
                }
            elif error_code in ("UnauthorizedOperation", "AccessDenied"):
                return {
                    "instance_id": instance_id,
                    "state": "access_denied",
                    "error": f"No permission for account '{account_name}'",
                }
            else:
                return {
                    "instance_id": instance_id,
                    "state": "error",
                    "error": f"AWS error: {error_code} - {e.response['Error']['Message']}",
                }

        except NoCredentialsError:
            return {
                "instance_id": instance_id,
                "state": "no_credentials",
                "error": f"No AWS credentials for account '{account_name}'",
            }

    async def get_multiple_statuses(
        self,
        servers: List[Dict[str, str]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get live status for multiple servers.
        Each entry should have: instance_id, account_name, region.
        Returns dict mapping instance_id → status info.
        """
        tasks = []
        for server in servers:
            instance_id = server.get("instance_id", "")
            account_name = server.get("account_name", "")
            region = server.get("region", settings.AWS_DEFAULT_REGION)

            if instance_id:
                tasks.append(
                    self.get_instance_status(instance_id, account_name, region)
                )

        if not tasks:
            return {}

        results = await asyncio.gather(*tasks, return_exceptions=True)

        status_map = {}
        for result in results:
            if isinstance(result, Exception):
                continue
            if isinstance(result, dict) and "instance_id" in result:
                status_map[result["instance_id"]] = result

        return status_map


# Singleton instance
aws_ec2_status_service = AWSEC2StatusService()
