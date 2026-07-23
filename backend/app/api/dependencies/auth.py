"""
Authentication Dependencies for FastAPI routes.
"""

from fastapi import Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.security import decode_access_token
from ...models.user import User, UserRole


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get the current authenticated user from the session/token."""
    # Try to get token from cookie or Authorization header
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user



async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require admin or super admin role."""
    admin_roles = [UserRole.ADMINISTRATOR, UserRole.SUPER_ADMINISTRATOR]
    if current_user.role not in admin_roles and not current_user.is_emergency_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_current_approver(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require approver role."""
    approver_roles = [
        UserRole.REPORTING_MANAGER,
        UserRole.CLOUD_MANAGER,
        UserRole.INFOSEC,
        UserRole.ADMINISTRATOR,
        UserRole.SUPER_ADMINISTRATOR,
    ]
    if current_user.role not in approver_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Approver access required",
        )
    return current_user
