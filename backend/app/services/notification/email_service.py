"""
Email Notification Service.
Handles sending all email notifications with configurable templates.
"""

import html
import logging
from typing import Optional, Dict, Any, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib
from jinja2 import Template

from ...core.config import settings

logger = logging.getLogger(__name__)


def _esc(value: Any) -> str:
    """HTML-escape a value for safe insertion into email templates."""
    return html.escape(str(value)) if value is not None else ""



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
        request_id = _esc(request_data['request_id'])
        access_type = _esc(request_data['access_type'])
        servers = _esc(request_data.get('servers', 'N/A'))

        subject = f"Access Request {request_id} Submitted"
        body = f"""
        <h2>Access Request Submitted</h2>
        <p>Your access request has been submitted successfully.</p>
        <table>
            <tr><td><b>Request ID:</b></td><td>{request_id}</td></tr>
            <tr><td><b>Type:</b></td><td>{access_type}</td></tr>
            <tr><td><b>Servers:</b></td><td>{servers}</td></tr>
            <tr><td><b>Status:</b></td><td>Pending Approval</td></tr>
        </table>
        <p>You will be notified of any updates.</p>
        """
        await self.send_email([request_data['requester_email']], subject, body)

    async def notify_approval_pending(self, approval_data: Dict[str, Any]):
        """Notify approver of pending approval."""
        request_id = _esc(approval_data['request_id'])
        requester_name = _esc(approval_data['requester_name'])
        access_type = _esc(approval_data['access_type'])
        servers = _esc(approval_data.get('servers', 'N/A'))
        justification = _esc(approval_data.get('justification', ''))

        subject = f"Approval Required: {request_id}"
        body = f"""
        <h2>Approval Required</h2>
        <p>A new access request requires your approval.</p>
        <table>
            <tr><td><b>Request ID:</b></td><td>{request_id}</td></tr>
            <tr><td><b>Requester:</b></td><td>{requester_name}</td></tr>
            <tr><td><b>Type:</b></td><td>{access_type}</td></tr>
            <tr><td><b>Servers:</b></td><td>{servers}</td></tr>
            <tr><td><b>Justification:</b></td><td>{justification}</td></tr>
        </table>
        <p>Please log in to the portal to approve or reject this request.</p>
        """
        await self.send_email([approval_data['approver_email']], subject, body)

    async def notify_request_approved(self, request_data: Dict[str, Any]):
        """Notify user that request was approved."""
        request_id = _esc(request_data['request_id'])
        access_type = _esc(request_data['access_type'])

        subject = f"Access Request {request_id} Approved"
        body = f"""
        <h2>Request Approved</h2>
        <p>Your access request has been fully approved and provisioning will begin shortly.</p>
        <table>
            <tr><td><b>Request ID:</b></td><td>{request_id}</td></tr>
            <tr><td><b>Type:</b></td><td>{access_type}</td></tr>
        </table>
        """
        await self.send_email([request_data['requester_email']], subject, body)

    async def notify_provisioning_complete(self, request_data: Dict[str, Any]):
        """Notify user of provisioning result with clear per-server breakdown."""
        all_success = request_data.get('success', False)
        succeeded = request_data.get('succeeded', 0)
        failed = request_data.get('failed', 0)
        total = request_data.get('total', 0)
        server_results = request_data.get('server_results', [])

        request_id = _esc(request_data['request_id'])

        if all_success:
            status_text = "Successful"
            header_color = "#22c55e"
        elif succeeded > 0:
            status_text = "Partially Successful"
            header_color = "#f59e0b"
        else:
            status_text = "Failed"
            header_color = "#ef4444"

        subject = f"Provisioning {status_text}: {request_id} ({succeeded}/{total} servers)"

        # Build per-server results table
        server_rows = ""
        for sr in server_results:
            server_name = _esc(sr.get('server', sr.get('hostname') or sr.get('ip_address', 'Unknown')))
            if sr.get('success'):
                status_badge = '<span style="color:#22c55e;font-weight:bold;">&#10003; SUCCESS</span>'
                detail = _esc(sr.get('message', 'Provisioned successfully'))
            else:
                status_badge = '<span style="color:#ef4444;font-weight:bold;">&#10007; FAILED</span>'
                error_type = sr.get('error_type', 'unknown')
                detail = _esc(sr.get('message', sr.get('error_detail', 'Unknown error')))
                if error_type == 'auth_failed':
                    detail = f"Authentication failed - {detail}"
                elif error_type == 'timeout':
                    detail = f"Connection timed out - {detail}"
                elif error_type == 'connection_failed':
                    detail = f"Connection failed - {detail}"
                elif error_type == 'script_failed':
                    exit_code = _esc(sr.get('exit_code', '?'))
                    detail = f"Script error (exit {exit_code}) - {detail}"

            server_rows += f"""
            <tr>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;font-family:monospace;">{server_name}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;">{status_badge}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;font-size:12px;color:#6b7280;">{detail}</td>
            </tr>"""

        body = f"""
        <div style="font-family:Arial,sans-serif;max-width:700px;">
            <h2 style="color:{header_color};">Provisioning {status_text}</h2>
            <table style="width:100%;margin-bottom:16px;">
                <tr><td><b>Request ID:</b></td><td>{request_id}</td></tr>
                <tr><td><b>Total Servers:</b></td><td>{total}</td></tr>
                <tr><td><b>Succeeded:</b></td><td style="color:#22c55e;font-weight:bold;">{succeeded}</td></tr>
                <tr><td><b>Failed:</b></td><td style="color:#ef4444;font-weight:bold;">{failed}</td></tr>
            </table>

            <h3>Per-Server Results</h3>
            <table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;">
                <thead>
                    <tr style="background-color:#f9fafb;">
                        <th style="padding:8px;text-align:left;border-bottom:2px solid #e5e7eb;">Server</th>
                        <th style="padding:8px;text-align:left;border-bottom:2px solid #e5e7eb;">Status</th>
                        <th style="padding:8px;text-align:left;border-bottom:2px solid #e5e7eb;">Details</th>
                    </tr>
                </thead>
                <tbody>
                    {server_rows}
                </tbody>
            </table>

            {f'<p style="margin-top:16px;color:#ef4444;"><b>Action Required:</b> Some servers failed provisioning. Please review the errors above and retry or contact your administrator.</p>' if failed > 0 else ''}
            {f'<p style="margin-top:16px;color:#22c55e;">All servers have been provisioned successfully.</p>' if all_success else ''}
        </div>
        """
        await self.send_email([request_data['requester_email']], subject, body)

    async def notify_sudo_expiry_reminder(self, request_data: Dict[str, Any]):
        """Notify user of upcoming sudo expiry."""
        request_id = _esc(request_data['request_id'])
        expiry_date = _esc(request_data.get('expiry_date', 'N/A'))

        subject = f"Sudo Access Expiring Soon: {request_id}"
        body = f"""
        <h2>Sudo Access Expiring Soon</h2>
        <p>Your sudo access will expire on {expiry_date}.</p>
        <p>Please submit a renewal request if you still need access.</p>
        <table>
            <tr><td><b>Request ID:</b></td><td>{request_id}</td></tr>
            <tr><td><b>Expiry Date:</b></td><td>{expiry_date}</td></tr>
        </table>
        """
        await self.send_email([request_data['requester_email']], subject, body)

    async def notify_sudo_expired(self, request_data: Dict[str, Any]):
        """Notify user that sudo has expired and been revoked."""
        request_id = _esc(request_data['request_id'])
        servers = _esc(request_data.get('servers', 'N/A'))

        subject = f"Sudo Access Expired: {request_id}"
        body = f"""
        <h2>Sudo Access Expired</h2>
        <p>Your sudo access has expired and been automatically revoked.</p>
        <table>
            <tr><td><b>Request ID:</b></td><td>{request_id}</td></tr>
            <tr><td><b>Servers:</b></td><td>{servers}</td></tr>
        </table>
        <p>Submit a new request if you need continued access.</p>
        """
        await self.send_email([request_data['requester_email']], subject, body)


# Singleton
email_service = EmailService()
