"""
Authentication Routes.
Handles Azure AD OAuth2 login and emergency admin login.
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...core.database import get_db
from ...core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from ...models.user import User, UserRole
from ...models.audit import AuditLog
from ...schemas.user import UserLogin, UserResponse
from ...services.auth.azure_ad import azure_ad_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Brute-force protection for emergency login
_failed_attempts: dict = defaultdict(list)
_LOCKOUT_THRESHOLD = 5
_LOCKOUT_DURATION = 900  # 15 minutes in seconds


def _check_brute_force(ip: str) -> None:
    """Check if IP is locked out due to too many failed attempts."""
    now = time.time()
    # Clean up old entries
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if now - t < _LOCKOUT_DURATION]
    if len(_failed_attempts[ip]) >= _LOCKOUT_THRESHOLD:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Please try again after 15 minutes.",
        )


def _record_failed_attempt(ip: str) -> None:
    """Record a failed login attempt for an IP."""
    _failed_attempts[ip].append(time.time())



@router.get("/login")
async def login(request: Request):
    """Initiate Azure AD login flow."""
    try:
        auth_flow = azure_ad_service.get_auth_url()
        request.session["auth_flow"] = auth_flow
        return {"auth_url": auth_flow.get("auth_uri", "")}
    except Exception as e:
        logger.error(f"Login initiation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.get("/callback")
async def callback(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Azure AD callback after authentication.
    Uses AD export file for employee details instead of Microsoft Graph API.
    """
    try:
        auth_flow = request.session.get("auth_flow", {})
        token_result = await azure_ad_service.acquire_token_by_code(
            auth_code_flow=auth_flow,
            auth_response=dict(request.query_params),
        )

        if not token_result or "access_token" not in token_result:
            raise HTTPException(status_code=401, detail="Authentication failed")

        # Extract email from the ID token claims (no Graph API call)
        id_token_claims = token_result.get("id_token_claims", {})
        user_email = (
            id_token_claims.get("preferred_username")
            or id_token_claims.get("email")
            or id_token_claims.get("upn")
            or ""
        ).lower()

        if not user_email:
            raise HTTPException(status_code=401, detail="Could not determine user email from token")

        azure_ad_id = id_token_claims.get("oid") or id_token_claims.get("sub", "")

        # Look up employee details from the daily AD export file
        from ...services.auth.ad_export_reader import ad_export_reader
        ad_profile = ad_export_reader.get_user_by_email(user_email)

        # Build profile from AD export (fallback to token claims if not found)
        display_name = ""
        department = ""
        job_title = ""
        employee_id = ""
        manager_email = ""
        manager_name = ""

        if ad_profile:
            display_name = ad_profile.get("display_name", "")
            department = ad_profile.get("department", "")
            job_title = ad_profile.get("job_title", "")
            employee_id = ad_profile.get("employee_id", "")
            manager_email = ad_profile.get("manager_email", "")
            manager_name = ad_profile.get("manager_name", "")
            logger.info(f"User profile loaded from AD export: {user_email}")
        else:
            # Fallback to token claims if AD export doesn't have the user
            display_name = id_token_claims.get("name", user_email.split("@")[0])
            logger.warning(f"User not found in AD export, using token claims: {user_email}")

        # Find or create user in local DB
        result = await db.execute(
            select(User).where(User.email == user_email)
        )
        user = result.scalar_one_or_none()

        if user:
            # Update user info from AD export
            user.display_name = display_name or user.display_name
            user.department = department or user.department
            user.job_title = job_title or user.job_title
            user.employee_id = employee_id or user.employee_id
            user.manager_email = manager_email or user.manager_email
            user.manager_name = manager_name or user.manager_name
            user.last_login = datetime.now(timezone.utc)
        else:
            # Create new user
            user = User(
                azure_ad_id=azure_ad_id,
                email=user_email,
                display_name=display_name or user_email.split("@")[0],
                department=department,
                job_title=job_title,
                employee_id=employee_id,
                manager_email=manager_email,
                manager_name=manager_name,
                role=UserRole.REQUESTER,
                last_login=datetime.now(timezone.utc),
            )
            db.add(user)
            await db.flush()

        # Create session token
        access_token = create_access_token({"sub": str(user.id), "email": user.email})

        # Audit log
        audit = AuditLog(
            user_id=user.id,
            user_email=user.email,
            user_name=user.display_name,
            action="login",
            resource_type="session",
            description="User logged in via Azure AD (profile from AD export)",
            ip_address=request.client.host if request.client else None,
        )
        db.add(audit)

        # Set cookie
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=settings.SESSION_TIMEOUT_MINUTES * 60,
        )

        return {
            "user": UserResponse.model_validate(user),
            "access_token": access_token,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Callback error: {str(e)}")
        raise HTTPException(status_code=500, detail="Authentication callback failed")



@router.post("/login/emergency")
async def emergency_login(
    login_data: UserLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Emergency admin login (local credentials)."""
    client_ip = request.client.host if request.client else "unknown"

    # Check brute-force lockout
    _check_brute_force(client_ip)

    # Validate username and password using bcrypt
    if (
        login_data.username != settings.EMERGENCY_ADMIN_USERNAME
        or not verify_password(login_data.password, settings.emergency_admin_password_hash)
    ):
        _record_failed_attempt(client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Find or create emergency admin
    result = await db.execute(
        select(User).where(User.email == f"{settings.EMERGENCY_ADMIN_USERNAME}@local")
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            email=f"{settings.EMERGENCY_ADMIN_USERNAME}@local",
            display_name="Emergency Administrator",
            role=UserRole.SUPER_ADMINISTRATOR,
            is_emergency_admin=True,
            last_login=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
    else:
        user.last_login = datetime.now(timezone.utc)

    access_token = create_access_token({"sub": str(user.id), "email": user.email})

    # Audit
    audit = AuditLog(
        user_id=user.id,
        user_email=user.email,
        user_name=user.display_name,
        action="emergency_login",
        resource_type="session",
        description="Emergency admin login",
    )
    db.add(audit)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.SESSION_TIMEOUT_MINUTES * 60,
    )

    return {"user": UserResponse.model_validate(user), "access_token": access_token}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Log out the current user."""
    response.delete_cookie("access_token")
    return {"message": "Logged out successfully"}


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh the access token before it expires.
    Returns a new token if the current one is still valid.
    """
    from ..dependencies.auth import get_current_user
    try:
        user = await get_current_user(request, db)
    except Exception:
        raise HTTPException(status_code=401, detail="Token expired, please login again")

    # Issue a new token
    new_token = create_access_token({"sub": str(user.id), "email": user.email})

    response.set_cookie(
        key="access_token",
        value=new_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.SESSION_TIMEOUT_MINUTES * 60,
    )

    return {"access_token": new_token, "expires_in": settings.SESSION_TIMEOUT_MINUTES * 60}


@router.get("/me")
async def get_current_user_info(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get current user info."""
    from ..dependencies.auth import get_current_user
    user = await get_current_user(request, db)
    return UserResponse.model_validate(user)
