"""
AWS Secrets Manager Integration.
Loads sensitive configuration values from AWS Secrets Manager at startup.
Also provides SSH key storage/retrieval from a separate SM secret.

All sensitive values (SECRET_KEY, SESSION_SECRET_KEY, ENCRYPTION_KEY,
EMERGENCY_ADMIN_PASSWORD, AZURE_CLIENT_SECRET, SMTP_PASSWORD) are stored
in AWS Secrets Manager and fetched on application boot.

SSH Private Keys are stored in a separate secret:
  - Secret Name: linux-access-portal/ssh-keys
  - Contains JSON: {"default": {"private_key": "...", "passphrase": "..."}, ...}

Configuration:
  - AWS_SECRETS_MANAGER_ENABLED=true     (enable/disable SM integration)
  - AWS_SECRETS_MANAGER_SECRET_NAME=linux-access-portal/config
  - AWS_SECRETS_MANAGER_SSH_KEY_SECRET=linux-access-portal/ssh-keys
  - AWS_SECRETS_MANAGER_REGION=us-east-1
  - AWS_SECRETS_MANAGER_PROFILE=         (optional AWS profile name)

The config secret in AWS Secrets Manager should be a JSON object like:
{
  "SECRET_KEY": "your-secure-random-key",
  "SESSION_SECRET_KEY": "your-session-key",
  "ENCRYPTION_KEY": "your-encryption-key",
  "EMERGENCY_ADMIN_PASSWORD": "your-secure-admin-password",
  "AZURE_CLIENT_SECRET": "your-azure-client-secret",
  "SMTP_PASSWORD": "your-smtp-password",
  "DATABASE_URL": "sqlite+aiosqlite:///./data/portal.db"
}

The SSH key secret should be a JSON object like:
{
  "default": {
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----",
    "passphrase": "optional-passphrase-or-empty",
    "key_type": "rsa"
  },
  "production-key": {
    "private_key": "-----BEGIN EC PRIVATE KEY-----\\n...\\n-----END EC PRIVATE KEY-----",
    "passphrase": "",
    "key_type": "ecdsa"
  }
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


# ============================================================
# SSH Private Key Storage in AWS Secrets Manager
# ============================================================

def get_ssh_key_secret_name() -> str:
    """Get the secret name for SSH keys."""
    return os.environ.get(
        "AWS_SECRETS_MANAGER_SSH_KEY_SECRET", "linux-access-portal/ssh-keys"
    )


def get_ssh_key_from_secrets_manager(key_name: str = "default") -> Optional[Dict[str, str]]:
    """
    Retrieve an SSH private key from AWS Secrets Manager.
    
    Args:
        key_name: Name of the key within the secret (e.g., "default", "production-key")
        
    Returns:
        Dict with 'private_key', 'passphrase', 'key_type' or None if not found.
    """
    if not is_secrets_manager_enabled():
        return None

    secret_name = get_ssh_key_secret_name()
    region = os.environ.get("AWS_SECRETS_MANAGER_REGION", "us-east-1")
    profile = os.environ.get("AWS_SECRETS_MANAGER_PROFILE", "")

    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        if profile:
            session = boto3.Session(profile_name=profile, region_name=region)
        else:
            session = boto3.Session(region_name=region)

        client = session.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_name)

        if "SecretString" in response:
            secret_data = json.loads(response["SecretString"])
        else:
            import base64
            secret_data = json.loads(base64.b64decode(response["SecretBinary"]).decode("utf-8"))

        if key_name in secret_data:
            key_data = secret_data[key_name]
            return {
                "private_key": key_data.get("private_key", ""),
                "passphrase": key_data.get("passphrase", ""),
                "key_type": key_data.get("key_type", "rsa"),
            }
        else:
            logger.warning(f"SSH key '{key_name}' not found in secret '{secret_name}'")
            return None

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            logger.warning(f"SSH key secret '{secret_name}' not found in Secrets Manager")
        else:
            logger.error(f"Failed to fetch SSH key from SM: {error_code}")
        return None
    except NoCredentialsError:
        logger.error("No AWS credentials for SSH key retrieval")
        return None
    except Exception as e:
        logger.error(f"Error fetching SSH key from Secrets Manager: {str(e)}")
        return None


def list_ssh_keys_from_secrets_manager() -> Dict[str, Dict[str, str]]:
    """
    List all SSH key names stored in AWS Secrets Manager.
    Returns dict mapping key_name → {key_type, has_passphrase}.
    Does NOT return the actual private key content.
    """
    if not is_secrets_manager_enabled():
        return {}

    secret_name = get_ssh_key_secret_name()
    region = os.environ.get("AWS_SECRETS_MANAGER_REGION", "us-east-1")
    profile = os.environ.get("AWS_SECRETS_MANAGER_PROFILE", "")

    try:
        import boto3
        from botocore.exceptions import ClientError

        if profile:
            session = boto3.Session(profile_name=profile, region_name=region)
        else:
            session = boto3.Session(region_name=region)

        client = session.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_name)

        if "SecretString" in response:
            secret_data = json.loads(response["SecretString"])
        else:
            import base64
            secret_data = json.loads(base64.b64decode(response["SecretBinary"]).decode("utf-8"))

        result = {}
        for key_name, key_data in secret_data.items():
            if isinstance(key_data, dict) and "private_key" in key_data:
                result[key_name] = {
                    "key_type": key_data.get("key_type", "unknown"),
                    "has_passphrase": bool(key_data.get("passphrase")),
                }
        return result

    except Exception as e:
        logger.error(f"Error listing SSH keys from Secrets Manager: {str(e)}")
        return {}


def store_ssh_key_in_secrets_manager(
    key_name: str,
    private_key: str,
    passphrase: str = "",
    key_type: str = "rsa",
) -> bool:
    """
    Store an SSH private key in AWS Secrets Manager.
    Updates the existing SSH keys secret with the new key.
    
    Args:
        key_name: Identifier for this key (e.g., "default", "production")
        private_key: The PEM-encoded private key content
        passphrase: Optional passphrase for the key
        key_type: Key type (rsa, ecdsa, ed25519)
        
    Returns:
        True if stored successfully, False otherwise.
    """
    if not is_secrets_manager_enabled():
        logger.warning("Cannot store SSH key in Secrets Manager - integration is disabled")
        return False

    secret_name = get_ssh_key_secret_name()
    region = os.environ.get("AWS_SECRETS_MANAGER_REGION", "us-east-1")
    profile = os.environ.get("AWS_SECRETS_MANAGER_PROFILE", "")

    try:
        import boto3
        from botocore.exceptions import ClientError

        if profile:
            session = boto3.Session(profile_name=profile, region_name=region)
        else:
            session = boto3.Session(region_name=region)

        client = session.client("secretsmanager")

        # Get existing secret data
        try:
            response = client.get_secret_value(SecretId=secret_name)
            if "SecretString" in response:
                secret_data = json.loads(response["SecretString"])
            else:
                secret_data = {}
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                # Create new secret
                secret_data = {}
            else:
                raise

        # Add/update the key
        secret_data[key_name] = {
            "private_key": private_key,
            "passphrase": passphrase,
            "key_type": key_type,
        }

        # Save back
        try:
            client.put_secret_value(
                SecretId=secret_name,
                SecretString=json.dumps(secret_data),
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                client.create_secret(
                    Name=secret_name,
                    Description="Enterprise Linux Access Portal - SSH Private Keys",
                    SecretString=json.dumps(secret_data),
                    Tags=[
                        {"Key": "Application", "Value": "Linux Access Portal"},
                        {"Key": "Type", "Value": "SSH Keys"},
                    ],
                )
            else:
                raise

        logger.info(f"SSH key '{key_name}' stored in Secrets Manager ({secret_name})")
        return True

    except Exception as e:
        logger.error(f"Failed to store SSH key in Secrets Manager: {str(e)}")
        return False


def delete_ssh_key_from_secrets_manager(key_name: str) -> bool:
    """
    Delete an SSH key from the Secrets Manager secret.
    """
    if not is_secrets_manager_enabled():
        return False

    secret_name = get_ssh_key_secret_name()
    region = os.environ.get("AWS_SECRETS_MANAGER_REGION", "us-east-1")
    profile = os.environ.get("AWS_SECRETS_MANAGER_PROFILE", "")

    try:
        import boto3
        from botocore.exceptions import ClientError

        if profile:
            session = boto3.Session(profile_name=profile, region_name=region)
        else:
            session = boto3.Session(region_name=region)

        client = session.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_name)

        if "SecretString" in response:
            secret_data = json.loads(response["SecretString"])
        else:
            return False

        if key_name in secret_data:
            del secret_data[key_name]
            client.put_secret_value(
                SecretId=secret_name,
                SecretString=json.dumps(secret_data),
            )
            logger.info(f"SSH key '{key_name}' deleted from Secrets Manager")
            return True
        return False

    except Exception as e:
        logger.error(f"Failed to delete SSH key from Secrets Manager: {str(e)}")
        return False
