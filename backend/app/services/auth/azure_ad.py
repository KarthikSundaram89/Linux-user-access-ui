"""
Azure AD Authentication Service.
Handles OAuth2 flow and Microsoft Graph API integration.
"""

import logging
from typing import Optional, Dict, Any

import httpx
import msal

from ...core.config import settings

logger = logging.getLogger(__name__)


class AzureADService:
    """Service for Azure AD OAuth2 authentication and Microsoft Graph API."""

    def __init__(self):
        self._msal_app: Optional[msal.ConfidentialClientApplication] = None

    @property
    def msal_app(self) -> msal.ConfidentialClientApplication:
        """Get or create MSAL confidential client application."""
        if self._msal_app is None:
            self._msal_app = msal.ConfidentialClientApplication(
                client_id=settings.AZURE_CLIENT_ID,
                client_credential=settings.AZURE_CLIENT_SECRET,
                authority=settings.azure_authority_url,
            )
        return self._msal_app

    def get_auth_url(self, state: Optional[str] = None) -> str:
        """Generate Azure AD authorization URL for SSO login."""
        scopes = settings.AZURE_SCOPES.split(",")
        flow = self.msal_app.initiate_auth_code_flow(
            scopes=scopes,
            redirect_uri=settings.AZURE_REDIRECT_URI,
            state=state,
        )
        return flow

    async def acquire_token_by_code(self, auth_code_flow: dict, auth_response: dict) -> Optional[dict]:
        """Exchange authorization code for tokens."""
        try:
            result = self.msal_app.acquire_token_by_auth_code_flow(
                auth_code_flow=auth_code_flow,
                auth_response=auth_response,
            )
            if "error" in result:
                logger.error(f"Token acquisition failed: {result.get('error_description')}")
                return None
            return result
        except Exception as e:
            logger.error(f"Token acquisition exception: {str(e)}")
            return None

    async def get_user_profile(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Fetch user profile from Microsoft Graph API."""
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            # Get basic profile
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=headers,
            )

            if response.status_code != 200:
                logger.error(f"Graph API profile fetch failed: {response.status_code}")
                return None

            profile = response.json()

            # Get manager info
            manager_info = await self._get_manager(client, headers)

            return {
                "azure_ad_id": profile.get("id"),
                "display_name": profile.get("displayName", ""),
                "email": profile.get("mail") or profile.get("userPrincipalName", ""),
                "department": profile.get("department"),
                "job_title": profile.get("jobTitle"),
                "employee_id": profile.get("employeeId"),
                "manager_email": manager_info.get("email") if manager_info else None,
                "manager_name": manager_info.get("name") if manager_info else None,
            }

    async def _get_manager(self, client: httpx.AsyncClient, headers: dict) -> Optional[Dict[str, str]]:
        """Fetch user's manager from Graph API."""
        try:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me/manager",
                headers=headers,
            )
            if response.status_code == 200:
                manager = response.json()
                return {
                    "email": manager.get("mail") or manager.get("userPrincipalName", ""),
                    "name": manager.get("displayName", ""),
                }
        except Exception as e:
            logger.warning(f"Could not fetch manager: {str(e)}")
        return None

    def validate_token(self, token: str) -> Optional[dict]:
        """Validate an Azure AD token."""
        try:
            accounts = self.msal_app.get_accounts()
            result = self.msal_app.acquire_token_silent(
                scopes=settings.AZURE_SCOPES.split(","),
                account=accounts[0] if accounts else None,
            )
            return result
        except Exception as e:
            logger.error(f"Token validation failed: {str(e)}")
            return None


# Singleton instance
azure_ad_service = AzureADService()
