"""
Enterprise Linux Access Self-Service Portal
Main FastAPI Application Entry Point.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .core.config import settings
from .core.database import init_db, close_db
from .services.scheduler import scheduler_service

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Create required directories
    for dir_path in [settings.DATA_DIR, settings.LOG_DIR, settings.UPLOAD_DIR, settings.SSH_KEY_PATH]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Start background scheduler
    scheduler_service.start()
    logger.info("Background scheduler started")

    # Initialize default data
    await _init_defaults()

    yield

    # Shutdown
    scheduler_service.stop()
    await close_db()
    logger.info("Application shutdown complete")


# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise Linux Access Self-Service Portal",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Session middleware (for Azure AD flow)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    max_age=settings.SESSION_TIMEOUT_MINUTES * 60,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Include API routes
from .api.routes import auth, requests, approvals, admin, reports

app.include_router(auth.router)
app.include_router(requests.router)
app.include_router(approvals.router)
app.include_router(admin.router)
app.include_router(reports.router)


# Health check
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "database": "connected",
        "scheduler": "running" if scheduler_service.is_running else "stopped",
    }


# Search endpoint
@app.get("/api/search")
async def search(
    q: str,
    field: str = None,
):
    """Global search across users, requests, servers."""
    from sqlalchemy import select, or_
    from .core.database import AsyncSessionLocal
    from .models.user import User
    from .models.request import AccessRequest, RequestServer

    async with AsyncSessionLocal() as db:
        results = {"users": [], "requests": [], "servers": []}

        # Search users
        user_result = await db.execute(
            select(User).where(
                or_(
                    User.email.ilike(f"%{q}%"),
                    User.display_name.ilike(f"%{q}%"),
                    User.department.ilike(f"%{q}%"),
                )
            ).limit(10)
        )
        results["users"] = [
            {"id": u.id, "email": u.email, "name": u.display_name}
            for u in user_result.scalars()
        ]

        # Search requests
        req_result = await db.execute(
            select(AccessRequest).where(
                or_(
                    AccessRequest.request_id.ilike(f"%{q}%"),
                    AccessRequest.application_name.ilike(f"%{q}%"),
                    AccessRequest.project_name.ilike(f"%{q}%"),
                )
            ).limit(10)
        )
        results["requests"] = [
            {"id": r.id, "request_id": r.request_id, "status": r.status.value}
            for r in req_result.scalars()
        ]

        # Search servers
        srv_result = await db.execute(
            select(RequestServer).where(
                or_(
                    RequestServer.hostname.ilike(f"%{q}%"),
                    RequestServer.ip_address.ilike(f"%{q}%"),
                )
            ).limit(10)
        )
        results["servers"] = [
            {"id": s.id, "hostname": s.hostname, "ip": s.ip_address}
            for s in srv_result.scalars()
        ]

    return results


# Serve frontend static files in production
frontend_path = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")



async def _init_defaults():
    """Initialize default configurations and admin user."""
    from .core.database import AsyncSessionLocal
    from .models.user import User, UserRole
    from .models.configuration import SystemConfiguration, ProvisioningScript
    from .core.security import hash_password

    async with AsyncSessionLocal() as db:
        # Check if emergency admin exists
        from sqlalchemy import select
        result = await db.execute(
            select(User).where(User.is_emergency_admin == True)
        )
        admin_exists = result.scalar_one_or_none()

        if not admin_exists:
            admin = User(
                email=f"{settings.EMERGENCY_ADMIN_USERNAME}@local",
                display_name="Emergency Administrator",
                role=UserRole.SUPER_ADMINISTRATOR,
                is_emergency_admin=True,
            )
            db.add(admin)

        # Default provisioning scripts
        result = await db.execute(select(ProvisioningScript))
        if not result.scalars().first():
            scripts = [
                ProvisioningScript(
                    name="Default User Creation",
                    script_type="user_creation",
                    script_content=(
                        "#!/bin/bash\n"
                        "useradd -m -s /bin/bash $username\n"
                        "echo 'User $username created on $hostname'\n"
                    ),
                    variables=["username", "hostname", "request_id"],
                ),
                ProvisioningScript(
                    name="Default Sudo Assignment",
                    script_type="sudo_assignment",
                    script_content=(
                        "#!/bin/bash\n"
                        "echo '$username ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/$username\n"
                        "chmod 440 /etc/sudoers.d/$username\n"
                        "echo 'Sudo granted to $username until $expiry_date'\n"
                    ),
                    variables=["username", "hostname", "expiry_date", "request_id"],
                ),
                ProvisioningScript(
                    name="Default Sudo Removal",
                    script_type="sudo_removal",
                    script_content=(
                        "#!/bin/bash\n"
                        "rm -f /etc/sudoers.d/$username\n"
                        "echo 'Sudo removed for $username on $hostname'\n"
                    ),
                    variables=["username", "hostname", "request_id"],
                ),
                ProvisioningScript(
                    name="Default Sudo Renewal",
                    script_type="renewal",
                    script_content=(
                        "#!/bin/bash\n"
                        "echo '$username ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/$username\n"
                        "chmod 440 /etc/sudoers.d/$username\n"
                        "echo 'Sudo renewed for $username until $expiry_date'\n"
                    ),
                    variables=["username", "hostname", "expiry_date", "request_id"],
                ),
            ]
            for script in scripts:
                db.add(script)

        await db.commit()
        logger.info("Default data initialized")
