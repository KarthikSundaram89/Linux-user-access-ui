"""
Email Notification Service.
Handles sending all email notifications with configurable templates.
"""

import logging
from typing import Optional, Dict, Any, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib
from jinja2 import Template

from ...core.config import settings

logger = logging.getLogger(__name__)



class EmailService:
    """Async email notification service with template support."""

    async def send_email(
        self,
        to_emails: List[str],
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
        cc: Optional[List[str]] = None,
    ) -> bool:
        """Send an email asynchronously."""
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg["To"] = ", ".join(to_emails)
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = ", ".join(cc)

            if body_text:
                msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))

            recipients = to_emails + (cc or [])

            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USERNAME or None,
                password=settings.SMTP_PASSWORD or None,
                use_tls=settings.SMTP_USE_TLS,
                recipients=recipients,
            )

            logger.info(f"Email sent to {', '.join(to_emails)}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Email send failed: {str(e)}")
            return False


    async def send_template_email(
        self,
        to_emails: List[str],
        template_subject: str,
        template_body: str,
        context: Dict[str, Any],
        cc: Optional[List[str]] = None,
    ) -> bool:
        """Send an email using a Jinja2 template."""
        try:
            subject = Template(template_subject).render(**context)
            body_html = Template(template_body).render(**context)
            return await self.send_email(to_emails, subject, body_html, cc=cc)
        except Exception as e:
            logger.error(f"Template email failed: {str(e)}")
            return False

    async def notify_request_submitted(self, request_data: Dict[str, Any]):
        """Notify user that request was submitted."""
        subject = f"Access Request {request_data['request_id']} Submitted"
        body = f"""
        <h2>Access Request Submitted</h2>
        <p>Your access request has been submitted successfully.</p>
        <table>
            <tr><td><b>Request ID:</b></td><td>{request_data['request_id']}</td></tr>
            <tr><td><b>Type:</b></td><td>{request_data['access_type']}</td></tr>
            <tr><td><b>Servers:</b></td><td>{request_data.get('servers', 'N/A')}</td></tr>
            <tr><td><b>Status:</b></td><td>Pending Approval</td></tr>
        </table>
        <p>You will be notified of any updates.</p>
        """
        await self.send_email([request_data['requester_email']], subject, body)

    async def notify_approval_pending(self, approval_data: Dict[str, Any]):
        """Notify approver of pending approval."""
        subject = f"Approval Required: {approval_data['request_id']}"
        body = f"""
        <h2>Approval Required</h2>
        <p>A new access request requires your approval.</p>
        <table>
            <tr><td><b>Request ID:</b></td><td>{approval_data['request_id']}</td></tr>
            <tr><td><b>Requester:</b></td><td>{approval_data['requester_name']}</td></tr>
            <tr><td><b>Type:</b></td><td>{approval_data['access_type']}</td></tr>
            <tr><td><b>Servers:</b></td><td>{approval_data.get('servers', 'N/A')}</td></tr>
            <tr><td><b>Justification:</b></td><td>{approval_data.get('justification', '')}</td></tr>
        </table>
        <p>Please log in to the portal to approve or reject this request.</p>
        """
        await self.send_email([approval_data['approver_email']], subject, body)

    async def notify_request_approved(self, request_data: Dict[str, Any]):
        """Notify user that request was approved."""
        subject = f"Access Request {request_data['request_id']} Approved"
        body = f"""
        <h2>Request Approved</h2>
        <p>Your access request has been fully approved and provisioning will begin shortly.</p>
        <table>
            <tr><td><b>Request ID:</b></td><td>{request_data['request_id']}</td></tr>
            <tr><td><b>Type:</b></td><td>{request_data['access_type']}</td></tr>
        </table>
        """
        await self.send_email([request_data['requester_email']], subject, body)

    async def notify_provisioning_complete(self, request_data: Dict[str, Any]):
        """Notify user of provisioning result."""
        status = "Successful" if request_data.get('success') else "Failed"
        subject = f"Provisioning {status}: {request_data['request_id']}"
        body = f"""
        <h2>Provisioning {status}</h2>
        <p>Provisioning for your request is complete.</p>
        <table>
            <tr><td><b>Request ID:</b></td><td>{request_data['request_id']}</td></tr>
            <tr><td><b>Succeeded:</b></td><td>{request_data.get('succeeded', 0)}</td></tr>
            <tr><td><b>Failed:</b></td><td>{request_data.get('failed', 0)}</td></tr>
        </table>
        """
        await self.send_email([request_data['requester_email']], subject, body)

    async def notify_sudo_expiry_reminder(self, request_data: Dict[str, Any]):
        """Notify user of upcoming sudo expiry."""
        subject = f"Sudo Access Expiring Soon: {request_data['request_id']}"
        body = f"""
        <h2>Sudo Access Expiring Soon</h2>
        <p>Your sudo access will expire on {request_data.get('expiry_date', 'N/A')}.</p>
        <p>Please submit a renewal request if you still need access.</p>
        <table>
            <tr><td><b>Request ID:</b></td><td>{request_data['request_id']}</td></tr>
            <tr><td><b>Expiry Date:</b></td><td>{request_data.get('expiry_date', 'N/A')}</td></tr>
        </table>
        """
        await self.send_email([request_data['requester_email']], subject, body)

    async def notify_sudo_expired(self, request_data: Dict[str, Any]):
        """Notify user that sudo has expired and been revoked."""
        subject = f"Sudo Access Expired: {request_data['request_id']}"
        body = f"""
        <h2>Sudo Access Expired</h2>
        <p>Your sudo access has expired and been automatically revoked.</p>
        <table>
            <tr><td><b>Request ID:</b></td><td>{request_data['request_id']}</td></tr>
            <tr><td><b>Servers:</b></td><td>{request_data.get('servers', 'N/A')}</td></tr>
        </table>
        <p>Submit a new request if you need continued access.</p>
        """
        await self.send_email([request_data['requester_email']], subject, body)


# Singleton
email_service = EmailService()
