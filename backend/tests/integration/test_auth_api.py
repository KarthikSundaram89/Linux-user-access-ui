"""
Integration tests for Authentication API endpoints.
Tests emergency admin login, token refresh, brute-force lockout.
"""

import time
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.core.config import settings


@pytest_asyncio.fixture
async def auth_client(db_session: AsyncSession):
    """Create a test client without authentication (for login tests)."""
    from app.main import app
    from app.core.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Set CSRF tokens for POST requests
        client.headers["X-CSRF-Token"] = "test-csrf-token"
        client.cookies.set("csrf_token", "test-csrf-token")
        yield client

    app.dependency_overrides.clear()


class TestEmergencyLogin:
    """Test emergency admin login endpoint."""

    @pytest.mark.asyncio
    async def test_emergency_login_success(self, auth_client, db_session):
        """Valid credentials should return token and user info."""
        # Clear brute-force tracking
        from app.api.routes.auth import _failed_attempts
        _failed_attempts.clear()

        # The test uses settings which has EMERGENCY_ADMIN_PASSWORD set
        # We need to mock verify_password to return True for our test password
        with patch("app.api.routes.auth.verify_password", return_value=True):
            response = await auth_client.post(
                "/api/auth/login/emergency",
                json={
                    "username": settings.EMERGENCY_ADMIN_USERNAME,
                    "password": settings.EMERGENCY_ADMIN_PASSWORD,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["role"] == "super_administrator"

    @pytest.mark.asyncio
    async def test_emergency_login_wrong_username(self, auth_client, db_session):
        """Wrong username should return 401."""
        from app.api.routes.auth import _failed_attempts
        _failed_attempts.clear()

        response = await auth_client.post(
            "/api/auth/login/emergency",
            json={"username": "wrong_user", "password": "any_password"},
        )
        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_emergency_login_wrong_password(self, auth_client, db_session):
        """Wrong password should return 401."""
        from app.api.routes.auth import _failed_attempts
        _failed_attempts.clear()

        response = await auth_client.post(
            "/api/auth/login/emergency",
            json={
                "username": settings.EMERGENCY_ADMIN_USERNAME,
                "password": "wrong_password_here",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_brute_force_lockout(self, auth_client, db_session):
        """5 failed attempts should trigger lockout (429)."""
        from app.api.routes.auth import _failed_attempts
        _failed_attempts.clear()

        # Make 5 failed attempts
        for i in range(5):
            response = await auth_client.post(
                "/api/auth/login/emergency",
                json={"username": "admin", "password": "wrong"},
            )
            # First 5 should be 401
            assert response.status_code == 401

        # 6th attempt should be rate-limited
        response = await auth_client.post(
            "/api/auth/login/emergency",
            json={"username": "admin", "password": "wrong"},
        )
        assert response.status_code == 429
        assert "Too many failed login attempts" in response.json()["detail"]

        # Cleanup
        _failed_attempts.clear()


class TestTokenRefresh:
    """Test token refresh endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_valid_token(self, db_session, test_user):
        """Valid token should be refreshed."""
        from app.main import app
        from app.core.database import get_db

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db

        token = create_access_token({"sub": str(test_user.id), "email": test_user.email})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.cookies.set("access_token", token)
            client.headers["X-CSRF-Token"] = "test-csrf"
            client.cookies.set("csrf_token", "test-csrf")

            response = await client.post("/api/auth/refresh")

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "expires_in" in data
        assert data["expires_in"] == settings.SESSION_TIMEOUT_MINUTES * 60

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_refresh_no_token_returns_401(self, auth_client, db_session):
        """No token should return 401."""
        response = await auth_client.post("/api/auth/refresh")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_returns_401(self, auth_client, db_session):
        """Invalid token should return 401."""
        auth_client.cookies.set("access_token", "invalid-token-value")
        response = await auth_client.post("/api/auth/refresh")
        assert response.status_code == 401


class TestLogout:
    """Test logout endpoint."""

    @pytest.mark.asyncio
    async def test_logout_success(self, test_client):
        """Logout should return success and clear cookie."""
        response = await test_client.post("/api/auth/logout")
        assert response.status_code == 200
        assert "Logged out" in response.json()["message"]


class TestGetCurrentUser:
    """Test /me endpoint."""

    @pytest.mark.asyncio
    async def test_get_me_authenticated(self, test_client, test_user):
        """Authenticated user should get their info."""
        response = await test_client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["display_name"] == test_user.display_name

    @pytest.mark.asyncio
    async def test_get_me_unauthenticated(self, auth_client):
        """Unauthenticated request should return 401."""
        response = await auth_client.get("/api/auth/me")
        assert response.status_code == 401
