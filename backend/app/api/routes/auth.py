"""
Authentication Routes.
Handles Azure AD OAuth2 login and emergency admin login.
"""

import logging
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
    """Handle Azure AD callback after authentication."""
    try:
        auth_flow = request.session.get("auth_flow", {})
        token_result = await azure_ad_service.acquire_token_by_code(
            auth_code_flow=auth_flow,
            auth_response=dict(request.query_params),
        )

        if not token_result or "access_token" not in token_result:
            raise HTTPException(status_code=401, detail="Authentication failed")

        # Fetch user profile from Microsoft Graph
        profile = await azure_ad_service.get_user_profile(token_result["access_token"])
        if not profile:
            raise HTTPException(status_code=401, detail="Could not fetch user profile")

        # Find or create user
        result = await db.execute(
            select(User).where(User.email == profile["email"])
        )
        user = result.scalar_one_or_none()

        if user:
            # Update user info
            user.display_name = profile["display_name"]
            user.department = profile.get("department")
            user.job_title = profile.get("job_title")
            user.manager_email = profile.get("manager_email")
            user.manager_name = profile.get("manager_name")
            user.last_login = datetime.now(timezone.utc)
        else:
            # Create new user
            user = User(
                azure_ad_id=profile["azure_ad_id"],
                email=profile["email"],
                display_name=profile["display_name"],
                department=profile.get("department"),
                job_title=profile.get("job_title"),
                employee_id=profile.get("employee_id"),
                manager_email=profile.get("manager_email"),
                manager_name=profile.get("manager_name"),
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
            description="User logged in via Azure AD",
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
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Emergency admin login (local credentials)."""
    if (
        login_data.username != settings.EMERGENCY_ADMIN_USERNAME
        or login_data.password != settings.EMERGENCY_ADMIN_PASSWORD
    ):
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


@router.get("/me")
async def get_current_user_info(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get current user info."""
    from ..dependencies.auth import get_current_user
    user = await get_current_user(request, db)
    return UserResponse.model_validate(user)
