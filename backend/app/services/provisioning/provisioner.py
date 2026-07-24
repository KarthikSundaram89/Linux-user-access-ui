"""
Provisioning Service - Orchestrates server provisioning.
Handles SSH and script failures gracefully, providing clear per-server results.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from string import Template

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.request import AccessRequest, RequestStatus, AccessType
from ...models.provisioning import ProvisioningTask, ProvisioningLog, ProvisioningStatus
from ...models.configuration import SSHKey, ProvisioningScript
from ...core.config import settings
from .ssh_engine import SSHEngine, SSHResult

logger = logging.getLogger(__name__)


class ServerProvisioningResult:
    """Detailed result for a single server provisioning attempt."""

    def __init__(self, hostname: str, ip_address: str = ""):
        self.hostname = hostname
        self.ip_address = ip_address
        self.server_identifier = hostname or ip_address
        self.success = False
        self.status = "pending"
        self.message = ""
        self.error_type = ""  # connection_failed, auth_failed, script_failed, timeout, unknown
        self.error_detail = ""
        self.stdout = ""
        self.stderr = ""
        self.exit_code = -1
        self.attempts = 0
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.duration_seconds = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server": self.server_identifier,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "success": self.success,
            "status": self.status,
            "message": self.message,
            "error_type": self.error_type,
            "error_detail": self.error_detail,
            "stdout": self.stdout[:500] if self.stdout else "",
            "stderr": self.stderr[:500] if self.stderr else "",
            "exit_code": self.exit_code,
            "attempts": self.attempts,
            "duration_seconds": self.duration_seconds,
        }


class ProvisioningService:
    """
    Orchestrates provisioning across multiple servers.
    Handles failures gracefully - continues provisioning remaining servers
    even if some fail. Provides clear per-server results.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ssh_engine = SSHEngine()

    async def provision_request(self, request: AccessRequest) -> Dict[str, Any]:
        """
        Provision all servers for an approved request.
        Returns detailed per-server results for the portal and email notification.
        """
        request.status = RequestStatus.PROVISIONING
        await self.db.flush()

        # Get SSH key
        ssh_key = await self._get_ssh_key()
        if not ssh_key:
            request.status = RequestStatus.PROVISIONING_FAILED
            return {
                "success": False,
                "error": "No SSH key configured. Please upload an SSH key in Admin > Configuration.",
                "total": len(request.servers),
                "succeeded": 0,
                "failed": len(request.servers),
                "server_results": [
                    ServerProvisioningResult(
                        hostname=s.hostname or "",
                        ip_address=s.ip_address or "",
                    ).to_dict()
                    for s in request.servers
                ],
            }

        # Get provisioning script
        script_template = await self._get_script(request.access_type)
        if not script_template:
            request.status = RequestStatus.PROVISIONING_FAILED
            return {
                "success": False,
                "error": "No provisioning script configured for this access type.",
                "total": len(request.servers),
                "succeeded": 0,
                "failed": len(request.servers),
                "server_results": [],
            }

        # Get requester username
        from ...models.user import User
        user_result = await self.db.execute(
            select(User).where(User.id == request.requester_id)
        )
        requester = user_result.scalar_one()
        username = requester.email.split("@")[0]

        # Provision each server (continue on failure)
        server_results: List[ServerProvisioningResult] = []

        for server in request.servers:
            hostname = server.hostname or server.ip_address
            result = await self._provision_single_server(
                request=request,
                server=server,
                hostname=hostname,
                username=username,
                script_template=script_template,
                ssh_key=ssh_key,
            )
            server_results.append(result)

        # Calculate summary
        success_count = sum(1 for r in server_results if r.success)
        total = len(server_results)

        # Update request status based on results
        if success_count == total:
            request.status = RequestStatus.PROVISIONED
            request.provisioned_at = datetime.now(timezone.utc)
            if request.access_type in [AccessType.SUDO_ACCESS, AccessType.BOTH, AccessType.RENEW_SUDO]:
                request.sudo_expiry_date = datetime.now(timezone.utc) + timedelta(
                    days=settings.SUDO_VALIDITY_DAYS
                )
        elif success_count > 0:
            request.status = RequestStatus.PARTIALLY_PROVISIONED
            # Still set sudo expiry for successful ones
            if request.access_type in [AccessType.SUDO_ACCESS, AccessType.BOTH, AccessType.RENEW_SUDO]:
                request.sudo_expiry_date = datetime.now(timezone.utc) + timedelta(
                    days=settings.SUDO_VALIDITY_DAYS
                )
        else:
            request.status = RequestStatus.PROVISIONING_FAILED

        await self.db.flush()

        return {
            "success": success_count == total,
            "total": total,
            "succeeded": success_count,
            "failed": total - success_count,
            "request_id": request.request_id,
            "requester_email": requester.email,
            "server_results": [r.to_dict() for r in server_results],
        }

    async def _provision_single_server(
        self,
        request: AccessRequest,
        server,
        hostname: str,
        username: str,
        script_template: str,
        ssh_key: SSHKey,
    ) -> ServerProvisioningResult:
        """
        Provision a single server with full error handling.
        Never raises - always returns a result (success or detailed failure).
        """
        result = ServerProvisioningResult(
            hostname=server.hostname or "",
            ip_address=server.ip_address or "",
        )
        result.started_at = datetime.now(timezone.utc)
        result.status = "in_progress"

        # Create provisioning task record
        task = ProvisioningTask(
            request_id=request.id,
            server_id=server.id,
            hostname=server.hostname,
            ip_address=server.ip_address,
            username=username,
            status=ProvisioningStatus.IN_PROGRESS,
            started_at=result.started_at,
        )
        self.db.add(task)
        await self.db.flush()

        try:
            # Prepare script with variables
            expiry_date = (
                datetime.now(timezone.utc) + timedelta(days=settings.SUDO_VALIDITY_DAYS)
            ).strftime("%Y-%m-%d")

            script = Template(script_template).safe_substitute(
                username=username,
                hostname=hostname,
                expiry_date=expiry_date,
                request_id=request.request_id,
            )

            # Execute via SSH
            ssh_result = await self.ssh_engine.execute_on_server(
                hostname=hostname,
                script=script,
                private_key_encrypted=ssh_key.private_key_encrypted,
                passphrase_encrypted=ssh_key.passphrase_encrypted,
            )

            result.attempts = ssh_result.exit_code if ssh_result.exit_code >= 0 else self.ssh_engine.max_retries
            result.stdout = ssh_result.stdout
            result.stderr = ssh_result.stderr
            result.exit_code = ssh_result.exit_code

            if ssh_result.success:
                result.success = True
                result.status = "success"
                result.message = f"Successfully provisioned on {hostname}"
                task.status = ProvisioningStatus.SUCCESS
                task.output = ssh_result.stdout[:2000]
                server.provisioning_status = "success"
                server.provisioned_at = datetime.now(timezone.utc)
                server.provisioning_message = "Provisioned successfully"
            else:
                result.success = False
                result.status = "failed"
                result.error_detail = ssh_result.error_message or ssh_result.stderr or "Unknown error"

                # Classify the error type for clear user feedback
                error_msg = (ssh_result.error_message or "").lower()
                if "authentication" in error_msg or "auth" in error_msg:
                    result.error_type = "auth_failed"
                    result.message = f"SSH authentication failed on {hostname}. Check SSH key permissions."
                elif "timed out" in error_msg or "timeout" in error_msg:
                    result.error_type = "timeout"
                    result.message = f"Connection to {hostname} timed out. Server may be unreachable."
                elif "connection refused" in error_msg or "no route" in error_msg:
                    result.error_type = "connection_failed"
                    result.message = f"Cannot connect to {hostname}. Server may be down or firewall is blocking."
                elif "all" in error_msg and "attempts failed" in error_msg:
                    result.error_type = "connection_failed"
                    result.message = f"All connection attempts to {hostname} failed after retries."
                elif ssh_result.exit_code > 0:
                    result.error_type = "script_failed"
                    result.message = f"Script execution failed on {hostname} (exit code: {ssh_result.exit_code})."
                else:
                    result.error_type = "unknown"
                    result.message = f"Provisioning failed on {hostname}: {result.error_detail[:200]}"

                task.status = ProvisioningStatus.FAILED
                task.error_message = result.message
                server.provisioning_status = "failed"
                server.provisioning_message = result.message

        except Exception as e:
            # Catch-all for unexpected errors
            result.success = False
            result.status = "failed"
            result.error_type = "unknown"
            result.error_detail = str(e)
            result.message = f"Unexpected error provisioning {hostname}: {str(e)[:200]}"

            task.status = ProvisioningStatus.FAILED
            task.error_message = result.message
            server.provisioning_status = "failed"
            server.provisioning_message = result.message

            logger.exception(f"Unexpected error provisioning {hostname}")

        # Finalize
        result.completed_at = datetime.now(timezone.utc)
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        task.completed_at = result.completed_at

        # Log the result
        log = ProvisioningLog(
            task_id=task.id,
            level="info" if result.success else "error",
            message=result.message,
            command=script_template[:300] if script_template else None,
            output=result.stdout[:2000] if result.stdout else None,
            error=result.error_detail[:2000] if result.error_detail else None,
        )
        self.db.add(log)

        return result


    async def _get_ssh_key(self) -> Optional[SSHKey]:
        """Get the default active SSH key."""
        result = await self.db.execute(
            select(SSHKey).where(SSHKey.is_active == True, SSHKey.is_default == True)
        )
        key = result.scalar_one_or_none()
        if not key:
            result = await self.db.execute(
                select(SSHKey).where(SSHKey.is_active == True)
            )
            key = result.scalar_one_or_none()
        return key

    async def _get_script(self, access_type: AccessType) -> Optional[str]:
        """Get the provisioning script template based on access type."""
        script_type_map = {
            AccessType.USER_ACCESS: "user_creation",
            AccessType.SUDO_ACCESS: "sudo_assignment",
            AccessType.BOTH: "user_creation",
            AccessType.RENEW_SUDO: "renewal",
        }
        script_type = script_type_map.get(access_type, "user_creation")

        result = await self.db.execute(
            select(ProvisioningScript).where(
                ProvisioningScript.script_type == script_type,
                ProvisioningScript.is_active == True,
            )
        )
        script = result.scalar_one_or_none()
        return script.script_content if script else None

    async def revoke_sudo(self, request: AccessRequest) -> dict:
        """Revoke sudo access for an expired request."""
        ssh_key = await self._get_ssh_key()
        if not ssh_key:
            return {"success": False, "error": "No SSH key configured"}

        # Get removal script
        result = await self.db.execute(
            select(ProvisioningScript).where(
                ProvisioningScript.script_type == "sudo_removal",
                ProvisioningScript.is_active == True,
            )
        )
        script_obj = result.scalar_one_or_none()
        if not script_obj:
            return {"success": False, "error": "No sudo removal script configured"}

        from ...models.user import User
        user_result = await self.db.execute(
            select(User).where(User.id == request.requester_id)
        )
        requester = user_result.scalar_one()
        username = requester.email.split("@")[0]

        revoked = 0
        for server in request.servers:
            hostname = server.hostname or server.ip_address
            script = Template(script_obj.script_content).safe_substitute(
                username=username,
                hostname=hostname,
                request_id=request.request_id,
            )
            ssh_result = await self.ssh_engine.execute_on_server(
                hostname=hostname,
                script=script,
                private_key_encrypted=ssh_key.private_key_encrypted,
                passphrase_encrypted=ssh_key.passphrase_encrypted,
            )
            if ssh_result.success:
                revoked += 1

        request.status = RequestStatus.REVOKED
        return {"success": True, "revoked": revoked, "total": len(request.servers)}
