"""
Background Scheduler Service.
Handles automatic sudo expiry checks, notifications, and revocations.
"""

import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...core.config import settings
from ...core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)



class SchedulerService:
    """Background scheduler for periodic tasks."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._running = False

    def start(self):
        """Start the background scheduler."""
        if self._running:
            return

        # Check sudo expiry daily
        self.scheduler.add_job(
            self.check_sudo_expiry,
            "interval",
            hours=settings.SUDO_EXPIRY_CHECK_INTERVAL_HOURS,
            id="check_sudo_expiry",
            name="Check Sudo Expiry",
            replace_existing=True,
        )

        # Send reminder notifications daily
        self.scheduler.add_job(
            self.send_expiry_reminders,
            "interval",
            hours=24,
            id="send_expiry_reminders",
            name="Send Expiry Reminders",
            replace_existing=True,
        )

        # Check approval timeouts every hour
        self.scheduler.add_job(
            self.check_approval_timeouts,
            "interval",
            hours=1,
            id="check_approval_timeouts",
            name="Check Approval Timeouts",
            replace_existing=True,
        )

        self.scheduler.start()
        self._running = True
        logger.info("Background scheduler started")

    def stop(self):
        """Stop the background scheduler."""
        if self._running:
            self.scheduler.shutdown()
            self._running = False
            logger.info("Background scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running


    async def check_sudo_expiry(self):
        """Check for expired sudo access and trigger revocation."""
        from ...models.request import AccessRequest, RequestStatus, AccessType
        from ...models.user import User
        from ..provisioning.provisioner import ProvisioningService
        from ..notification.email_service import email_service

        logger.info("Running sudo expiry check...")

        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(
                select(AccessRequest)
                .options(selectinload(AccessRequest.servers))
                .where(
                    AccessRequest.sudo_expiry_date <= now,
                    AccessRequest.status == RequestStatus.PROVISIONED,
                    AccessRequest.access_type.in_([
                        AccessType.SUDO_ACCESS,
                        AccessType.BOTH,
                        AccessType.RENEW_SUDO,
                    ]),
                )
            )
            expired_requests = result.scalars().all()

            for request in expired_requests:
                logger.info(f"Revoking sudo for expired request: {request.request_id}")
                provisioner = ProvisioningService(db)
                revoke_result = await provisioner.revoke_sudo(request)

                # Get requester info
                user_result = await db.execute(
                    select(User).where(User.id == request.requester_id)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    servers = ", ".join(
                        s.hostname or s.ip_address for s in request.servers
                    )
                    await email_service.notify_sudo_expired({
                        "request_id": request.request_id,
                        "requester_email": user.email,
                        "servers": servers,
                    })

            await db.commit()
            logger.info(f"Sudo expiry check complete. Revoked: {len(expired_requests)}")


    async def send_expiry_reminders(self):
        """Send reminders for sudo access expiring within reminder period."""
        from ...models.request import AccessRequest, RequestStatus, AccessType
        from ...models.user import User
        from ..notification.email_service import email_service

        logger.info("Running expiry reminder check...")

        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            reminder_threshold = now + timedelta(days=settings.SUDO_REMINDER_DAYS)

            result = await db.execute(
                select(AccessRequest)
                .where(
                    AccessRequest.sudo_expiry_date <= reminder_threshold,
                    AccessRequest.sudo_expiry_date > now,
                    AccessRequest.status == RequestStatus.PROVISIONED,
                    AccessRequest.access_type.in_([
                        AccessType.SUDO_ACCESS,
                        AccessType.BOTH,
                        AccessType.RENEW_SUDO,
                    ]),
                )
            )
            expiring_requests = result.scalars().all()

            for request in expiring_requests:
                user_result = await db.execute(
                    select(User).where(User.id == request.requester_id)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    await email_service.notify_sudo_expiry_reminder({
                        "request_id": request.request_id,
                        "requester_email": user.email,
                        "expiry_date": request.sudo_expiry_date.strftime("%Y-%m-%d"),
                    })

            logger.info(f"Sent {len(expiring_requests)} expiry reminders")

    async def check_approval_timeouts(self):
        """Check for timed-out approval steps."""
        from ..approval.approval_engine import ApprovalEngine

        logger.info("Checking approval timeouts...")

        async with AsyncSessionLocal() as db:
            engine = ApprovalEngine(db)
            await engine.check_timeouts()
            await db.commit()

        logger.info("Approval timeout check complete")


# Singleton
scheduler_service = SchedulerService()
