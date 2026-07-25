"""
AWS Secrets Manager Integration.
Loads sensitive configuration values from AWS Secrets Manager at startup.

All sensitive values (SECRET_KEY, SESSION_SECRET_KEY, ENCRYPTION_KEY,
EMERGENCY_ADMIN_PASSWORD, AZURE_CLIENT_SECRET, SMTP_PASSWORD) are stored
in AWS Secrets Manager and fetched on application boot.

Configuration:
  - AWS_SECRETS_MANAGER_ENABLED=true     (enable/disable SM integration)
  - AWS_SECRETS_MANAGER_SECRET_NAME=linux-access-portal/config
  - AWS_SECRETS_MANAGER_REGION=us-east-1
  - AWS_SECRETS_MANAGER_PROFILE=         (optional AWS profile name)

The secret in AWS Secrets Manager should be a JSON object like:
{
  "SECRET_KEY": "your-secure-random-key",
  "SESSION_SECRET_KEY": "your-session-key",
  "ENCRYPTION_KEY": "your-encryption-key",
  "EMERGENCY_ADMIN_PASSWORD": "your-secure-admin-password",
  "AZURE_CLIENT_SECRET": "your-azure-client-secret",
  "SMTP_PASSWORD": "your-smtp-password",
  "DATABASE_URL": "sqlite+aiosqlite:///./data/portal.db"
}
"""

import json
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Sensitive keys that should be stored in Secrets Manager
SENSITIVE_KEYS = [
    "SECRET_KEY",
    "SESSION_SECRET_KEY",
    "ENCRYPTION_KEY",
    "EMERGENCY_ADMIN_PASSWORD",
    "AZURE_CLIENT_SECRET",
    "SMTP_PASSWORD",
    "DATABASE_URL",
]


def is_secrets_manager_enabled() -> bool:
    """Check if AWS Secrets Manager integration is enabled."""
    return os.environ.get("AWS_SECRETS_MANAGER_ENABLED", "false").lower() in ("true", "1", "yes")


def get_secrets_from_aws() -> Dict[str, str]:
    """
    Fetch secrets from AWS Secrets Manager.
    Returns a dict of key-value pairs.
    Raises RuntimeError if secrets cannot be fetched.
    """
    secret_name = os.environ.get(
        "AWS_SECRETS_MANAGER_SECRET_NAME", "linux-access-portal/config"
    )
    region = os.environ.get("AWS_SECRETS_MANAGER_REGION", "us-east-1")
    profile = os.environ.get("AWS_SECRETS_MANAGER_PROFILE", "")

    logger.info(f"Fetching secrets from AWS Secrets Manager: {secret_name} (region: {region})")

    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        # Create session with optional profile
        if profile:
            session = boto3.Session(profile_name=profile, region_name=region)
        else:
            session = boto3.Session(region_name=region)

        client = session.client("secretsmanager")

        response = client.get_secret_value(SecretId=secret_name)

        # Secret can be a string or binary
        if "SecretString" in response:
            secret_string = response["SecretString"]
        else:
            import base64
            secret_string = base64.b64decode(response["SecretBinary"]).decode("utf-8")

        # Parse JSON
        secrets = json.loads(secret_string)

        if not isinstance(secrets, dict):
            raise RuntimeError(f"Secret '{secret_name}' is not a JSON object")

        logger.info(f"Successfully loaded {len(secrets)} secret(s) from AWS Secrets Manager")
        return secrets

    except ImportError:
        raise RuntimeError(
            "boto3 is required for AWS Secrets Manager integration. "
            "Install with: pip install boto3"
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            raise RuntimeError(
                f"Secret '{secret_name}' not found in AWS Secrets Manager. "
                f"Create it with: aws secretsmanager create-secret --name {secret_name} --secret-string '{{...}}'"
            )
        elif error_code in ("AccessDeniedException", "UnauthorizedOperation"):
            raise RuntimeError(
                f"Access denied to secret '{secret_name}'. "
                f"Ensure the EC2 instance role or configured profile has secretsmanager:GetSecretValue permission."
            )
        else:
            raise RuntimeError(f"AWS Secrets Manager error ({error_code}): {e.response['Error']['Message']}")
    except NoCredentialsError:
        raise RuntimeError(
            "No AWS credentials found. Configure credentials via IAM role (EC2), "
            "environment variables (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY), "
            "or AWS CLI profile (AWS_SECRETS_MANAGER_PROFILE)."
        )
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Secret '{secret_name}' contains invalid JSON: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Failed to fetch secrets from AWS Secrets Manager: {str(e)}")


def load_secrets_into_environment():
    """
    Load secrets from AWS Secrets Manager and inject them as environment variables.
    Must be called BEFORE Settings() is instantiated.

    Only sets env vars for keys that are not already set in the environment
    (allowing local .env overrides for development).
    """
    if not is_secrets_manager_enabled():
        logger.info("AWS Secrets Manager integration is DISABLED (set AWS_SECRETS_MANAGER_ENABLED=true to enable)")
        return

    secrets = get_secrets_from_aws()

    injected = 0
    for key, value in secrets.items():
        if not value:
            continue

        # Only inject if not already set in environment (env vars take precedence)
        if key not in os.environ or not os.environ[key]:
            os.environ[key] = str(value)
            injected += 1
            # Log the key name but never the value
            logger.debug(f"Injected secret: {key}")
        else:
            logger.debug(f"Secret '{key}' already set in environment, skipping")

    logger.info(f"AWS Secrets Manager: injected {injected} secret(s) into environment")


def validate_sensitive_keys_present():
    """
    Validate that all sensitive keys have values after loading.
    Returns list of missing keys.
    """
    missing = []
    for key in SENSITIVE_KEYS:
        value = os.environ.get(key, "")
        if not value:
            missing.append(key)
    return missing


def create_secret_template() -> str:
    """
    Generate a template JSON for creating the secret in AWS Secrets Manager.
    Useful for initial setup.
    """
    import secrets as secrets_module

    template = {
        "SECRET_KEY": secrets_module.token_hex(32),
        "SESSION_SECRET_KEY": secrets_module.token_hex(32),
        "ENCRYPTION_KEY": secrets_module.token_hex(32),
        "EMERGENCY_ADMIN_PASSWORD": secrets_module.token_hex(16),
        "AZURE_CLIENT_SECRET": "your-azure-client-secret-here",
        "SMTP_PASSWORD": "your-smtp-password-here",
        "DATABASE_URL": "sqlite+aiosqlite:///./data/portal.db",
    }
    return json.dumps(template, indent=2)
