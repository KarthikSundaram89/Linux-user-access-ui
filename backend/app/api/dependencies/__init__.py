"""API Dependencies Package."""
from .auth import get_current_user, get_current_admin_user

__all__ = ["get_current_user", "get_current_admin_user"]
