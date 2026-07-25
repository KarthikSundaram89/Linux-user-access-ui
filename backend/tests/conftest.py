"""
Shared test fixtures for the Enterprise Linux Access Portal backend tests.
Provides async DB session, test client, mock user, and mock settings.
"""

import os
import sys

# Set test environment variables BEFORE any app imports
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only-32chars!"
os.environ["SESSION_SECRET_KEY"] = "test-session-secret-key-32chars!!"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-for-testing!!"
os.environ["EMERGENCY_ADMIN_PASSWORD"] = "TestAdminP@ss123!"
os.environ["EMERGENCY_ADMIN_USERNAME"] = "admin"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_portal.db"
os.environ["AWS_SECRETS_MANAGER_ENABLED"] = "false"
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_PORT"] = "587"
os.environ["AD_EXPORT_PATH"] = "/tmp/test_ad_exports"
os.environ["EC2_INVENTORY_PATH"] = "/tmp/test_ec2_inventory"
os.environ["SSH_KEY_PATH"] = "/tmp/test_ssh_keys"
os.environ["DATA_DIR"] = "/tmp/test_data"
os.environ["LOG_DIR"] = "/tmp/test_logs"
os.environ["UPLOAD_DIR"] = "/tmp/test_uploads"

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from httpx import AsyncClient, ASGITransport

# Now import app modules
from app.core.database import Base
from app.models.user import User, UserRole
from app.models.request import AccessRequest, RequestServer, RequestStatus, AccessType, EnvironmentType
from app.models.approval import ApprovalStep, ApprovalAction, ApprovalStatus, ApprovalType
from app.models.provisioning import ProvisioningTask, ProvisioningLog, ProvisioningStatus
from app.models.configuration import SSHKey, ProvisioningScript, ApprovalWorkflowConfig
from app.core.security import create_access_token


# Test database engine (in-memory SQLite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture
async def db_session():
    """Provide a clean async database session for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session
        await session.rollback()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user in the database."""
    user = User(
        email="testuser@company.com",
        display_name="Test User",
        department="Engineering",
        job_title="Developer",
        employee_id="EMP001",
        manager_email="manager@company.com",
        manager_name="Test Manager",
        role=UserRole.REQUESTER,
        is_active=True,
        last_login=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession):
    """Create a test admin user in the database."""
    user = User(
        email="admin@local",
        display_name="Emergency Administrator",
        role=UserRole.SUPER_ADMINISTRATOR,
        is_active=True,
        is_emergency_admin=True,
        last_login=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def approver_user(db_session: AsyncSession):
    """Create a test approver user."""
    user = User(
        email="approver@company.com",
        display_name="Test Approver",
        department="Cloud Team",
        role=UserRole.CLOUD_MANAGER,
        is_active=True,
        last_login=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user):
    """Create a valid JWT token for the test user."""
    return create_access_token({"sub": str(test_user.id), "email": test_user.email})


@pytest.fixture
def admin_token(admin_user):
    """Create a valid JWT token for the admin user."""
    return create_access_token({"sub": str(admin_user.id), "email": admin_user.email})


@pytest_asyncio.fixture
async def sample_request(db_session: AsyncSession, test_user: User):
    """Create a sample access request."""
    from app.core.security import generate_request_id

    request = AccessRequest(
        request_id=generate_request_id(),
        requester_id=test_user.id,
        access_type=AccessType.USER_ACCESS,
        environment=EnvironmentType.PRODUCTION,
        purpose="Need access for deployment tasks and server maintenance",
        business_justification="Required for Q1 release deployment and ongoing operations",
        application_name="TestApp",
        project_name="TestProject",
        status=RequestStatus.PENDING_APPROVAL,
    )
    db_session.add(request)
    await db_session.flush()

    server = RequestServer(
        request_id=request.id,
        ip_address="10.10.10.5",
        provisioning_status="pending",
    )
    db_session.add(server)
    await db_session.flush()
    await db_session.refresh(request, ["servers"])
    return request


@pytest_asyncio.fixture
async def test_client(db_session: AsyncSession, test_user: User):
    """Create an HTTP test client with authentication and a fresh DB."""
    from app.main import app
    from app.core.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    token = create_access_token({"sub": str(test_user.id), "email": test_user.email})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set("access_token", token)
        client.headers["X-CSRF-Token"] = "test-csrf-token"
        client.cookies.set("csrf_token", "test-csrf-token")
        yield client

    app.dependency_overrides.clear()
