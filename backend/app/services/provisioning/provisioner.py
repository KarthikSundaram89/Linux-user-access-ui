"""
Provisioning Service - Orchestrates server provisioning.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from string import Template

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.request import AccessRequest, RequestStatus, AccessType
from ...models.provisioning import ProvisioningTask, ProvisioningLog, ProvisioningStatus
from ...models.configuration import SSHKey, ProvisioningScript
from ...core.config import settings
from .ssh_engine import SSHEngine, SSHResult

logger = logging.getLogger(__name__)



class ProvisioningService:
    """Orchestrates provisioning across multiple servers."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ssh_engine = SSHEngine()

    async def provision_request(self, request: AccessRequest) -> dict:
        """
        Provision all servers for an approved request.
        Returns summary of results.
        """
        request.status = RequestStatus.PROVISIONING
        await self.db.flush()

        # Get SSH key
        ssh_key = await self._get_ssh_key()
        if not ssh_key:
            request.status = RequestStatus.PROVISIONING_FAILED
            return {"success": False, "error": "No SSH key configured"}

        # Get provisioning script
        script_template = await self._get_script(request.access_type)
        if not script_template:
            request.status = RequestStatus.PROVISIONING_FAILED
            return {"success": False, "error": "No provisioning script configured"}

        # Get requester username
        from ...models.user import User
        user_result = await self.db.execute(
            select(User).where(User.id == request.requester_id)
        )
        requester = user_result.scalar_one()
        username = requester.email.split("@")[0]

        results = []
        for server in request.servers:
            hostname = server.hostname or server.ip_address


            # Create provisioning task
            task = ProvisioningTask(
                request_id=request.id,
                server_id=server.id,
                hostname=server.hostname,
                ip_address=server.ip_address,
                username=username,
                status=ProvisioningStatus.IN_PROGRESS,
                started_at=datetime.now(timezone.utc),
            )
            self.db.add(task)
            await self.db.flush()

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
            result = await self.ssh_engine.execute_on_server(
                hostname=hostname,
                script=script,
                private_key_encrypted=ssh_key.private_key_encrypted,
                passphrase_encrypted=ssh_key.passphrase_encrypted,
            )

            # Log result
            log = ProvisioningLog(
                task_id=task.id,
                level="info" if result.success else "error",
                message=f"Provisioning {'succeeded' if result.success else 'failed'}",
                command=script[:500],
                output=result.stdout[:2000] if result.stdout else None,
                error=result.stderr[:2000] if result.stderr else None,
            )
            self.db.add(log)


            # Update task status
            if result.success:
                task.status = ProvisioningStatus.SUCCESS
                task.output = result.stdout
                server.provisioning_status = "success"
                server.provisioned_at = datetime.now(timezone.utc)
            else:
                task.status = ProvisioningStatus.FAILED
                task.error_message = result.error_message or result.stderr
                server.provisioning_status = "failed"
                server.provisioning_message = result.error_message

            task.completed_at = datetime.now(timezone.utc)
            results.append(result)

        # Update request status
        success_count = sum(1 for r in results if r.success)
        total = len(results)

        if success_count == total:
            request.status = RequestStatus.PROVISIONED
            request.provisioned_at = datetime.now(timezone.utc)
            if request.access_type in [AccessType.SUDO_ACCESS, AccessType.BOTH, AccessType.RENEW_SUDO]:
                request.sudo_expiry_date = datetime.now(timezone.utc) + timedelta(
                    days=settings.SUDO_VALIDITY_DAYS
                )
        elif success_count > 0:
            request.status = RequestStatus.PARTIALLY_PROVISIONED
        else:
            request.status = RequestStatus.PROVISIONING_FAILED

        await self.db.flush()

        return {
            "success": success_count == total,
            "total": total,
            "succeeded": success_count,
            "failed": total - success_count,
        }


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
