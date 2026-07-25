"""
Unit tests for the Email Service.
Tests HTML sanitization in emails, template rendering.
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from app.services.notification.email_service import EmailService, _esc


class TestHTMLEscaping:
    """Test HTML sanitization in email content."""

    def test_escape_html_tags(self):
        """Should escape HTML tags to prevent XSS."""
        malicious = "<script>alert('xss')</script>"
        escaped = _esc(malicious)
        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped

    def test_escape_ampersand(self):
        """Should escape ampersands."""
        text = "A & B"
        escaped = _esc(text)
        assert "&amp;" in escaped

    def test_escape_quotes(self):
        """Should escape quotes."""
        text = 'He said "hello"'
        escaped = _esc(text)
        assert "&quot;" in escaped

    def test_escape_angle_brackets(self):
        """Should escape angle brackets."""
        text = "value > 5 and value < 10"
        escaped = _esc(text)
        assert "&gt;" in escaped
        assert "&lt;" in escaped

    def test_escape_none_returns_empty(self):
        """None should return empty string."""
        escaped = _esc(None)
        assert escaped == ""

    def test_escape_normal_text_unchanged(self):
        """Normal text without special characters should pass through."""
        text = "Normal request for server access"
        escaped = _esc(text)
        assert escaped == text

    def test_escape_numeric_value(self):
        """Numeric values should be converted to string."""
        escaped = _esc(42)
        assert escaped == "42"


class TestEmailServiceSend:
    """Test email sending functionality."""

    @pytest.mark.asyncio
    async def test_send_email_calls_smtp(self):
        """send_email should attempt SMTP send."""
        service = EmailService()

        with patch("app.services.notification.email_service.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = None
            result = await service.send_email(
                to_emails=["user@test.com"],
                subject="Test Subject",
                body_html="<p>Hello</p>",
            )
            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_handles_failure(self):
        """send_email should return False on failure."""
        service = EmailService()

        with patch("app.services.notification.email_service.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = Exception("SMTP connection failed")
            result = await service.send_email(
                to_emails=["user@test.com"],
                subject="Test",
                body_html="<p>Test</p>",
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_send_template_email(self):
        """send_template_email should render Jinja2 templates."""
        service = EmailService()

        with patch("app.services.notification.email_service.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = None
            result = await service.send_template_email(
                to_emails=["user@test.com"],
                template_subject="Request {{ request_id }}",
                template_body="<p>Hello {{ name }}</p>",
                context={"request_id": "LAR-123", "name": "John"},
            )
            assert result is True


class TestEmailNotifications:
    """Test specific email notification methods."""

    @pytest.mark.asyncio
    async def test_notify_request_submitted_sanitizes(self):
        """Request submitted notification should sanitize user input."""
        service = EmailService()

        with patch.object(service, "send_email", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await service.notify_request_submitted({
                "request_id": "LAR-<script>alert(1)</script>",
                "requester_email": "user@test.com",
                "access_type": "user_access",
                "servers": "10.10.10.5",
            })
            mock_send.assert_called_once()
            # Check that the HTML body is sanitized
            call_args = mock_send.call_args
            body_html = call_args[1].get("body_html", call_args[0][2] if len(call_args[0]) > 2 else "")
            assert "<script>" not in body_html

    @pytest.mark.asyncio
    async def test_notify_provisioning_complete_success(self):
        """Provisioning notification should show success status."""
        service = EmailService()

        with patch.object(service, "send_email", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await service.notify_provisioning_complete({
                "request_id": "LAR-20240101-ABCD1234",
                "requester_email": "user@test.com",
                "success": True,
                "succeeded": 2,
                "failed": 0,
                "total": 2,
                "server_results": [
                    {"server": "10.0.0.1", "success": True, "message": "OK"},
                    {"server": "10.0.0.2", "success": True, "message": "OK"},
                ],
            })
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            subject = call_args[1].get("subject", call_args[0][1] if len(call_args[0]) > 1 else "")
            assert "Successful" in subject

    @pytest.mark.asyncio
    async def test_notify_provisioning_complete_partial_failure(self):
        """Provisioning notification should show partial success."""
        service = EmailService()

        with patch.object(service, "send_email", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await service.notify_provisioning_complete({
                "request_id": "LAR-20240101-ABCD1234",
                "requester_email": "user@test.com",
                "success": False,
                "succeeded": 1,
                "failed": 1,
                "total": 2,
                "server_results": [
                    {"server": "10.0.0.1", "success": True, "message": "OK"},
                    {"server": "10.0.0.2", "success": False, "message": "Timeout", "error_type": "timeout"},
                ],
            })
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            subject = call_args[1].get("subject", call_args[0][1] if len(call_args[0]) > 1 else "")
            assert "Partially" in subject

    @pytest.mark.asyncio
    async def test_notify_approval_pending_sanitizes(self):
        """Approval pending notification should sanitize all fields."""
        service = EmailService()

        with patch.object(service, "send_email", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await service.notify_approval_pending({
                "request_id": "LAR-20240101-ABCD",
                "requester_name": "User <img src=x onerror=alert(1)>",
                "access_type": "sudo_access",
                "servers": "10.10.10.5",
                "justification": "I need 'special' access & more",
                "approver_email": "approver@test.com",
            })
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            body_html = call_args[1].get("body_html", call_args[0][2] if len(call_args[0]) > 2 else "")
            assert "<img" not in body_html
            assert "&amp;" in body_html

    @pytest.mark.asyncio
    async def test_notify_sudo_expiry_reminder(self):
        """Sudo expiry reminder should include expiry date."""
        service = EmailService()

        with patch.object(service, "send_email", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await service.notify_sudo_expiry_reminder({
                "request_id": "LAR-20240101-ABCD",
                "requester_email": "user@test.com",
                "expiry_date": "2024-03-15",
            })
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            body_html = call_args[1].get("body_html", call_args[0][2] if len(call_args[0]) > 2 else "")
            assert "2024-03-15" in body_html
