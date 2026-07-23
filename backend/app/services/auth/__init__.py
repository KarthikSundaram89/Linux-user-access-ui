"""Authentication service package."""
from .azure_ad import AzureADService, azure_ad_service

__all__ = ["AzureADService", "azure_ad_service"]
