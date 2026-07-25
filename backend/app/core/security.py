"""
Security utilities - encryption, hashing, token management.
"""

import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext
from cryptography.fernet import Fernet

from .config import settings


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Encryption key for sensitive data (SSH keys, secrets)
_fernet_key: Optional[Fernet] = None


def get_fernet() -> Fernet:
    """Get or create Fernet encryption instance."""
    global _fernet_key
    if _fernet_key is None:
        import logging
        _logger = logging.getLogger(__name__)
        encryption_source = settings.ENCRYPTION_KEY
        if encryption_source:
            _logger.info("Using dedicated ENCRYPTION_KEY for data encryption")
        else:
            _logger.warning(
                "ENCRYPTION_KEY not set; falling back to SECRET_KEY for encryption. "
                "Set ENCRYPTION_KEY to allow independent key rotation."
            )
            encryption_source = settings.SECRET_KEY
        key = hashlib.sha256(encryption_source.encode()).digest()
        import base64
        _fernet_key = Fernet(base64.urlsafe_b64encode(key[:32]))
    return _fernet_key


def encrypt_value(value: str) -> str:
    """Encrypt a sensitive value."""
    f = get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a sensitive value."""
    f = get_fernet()
    return f.decrypt(encrypted.encode()).decode()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.SESSION_TIMEOUT_MINUTES))
    to_encode.update({
        "exp": expire,
        "iss": "linux-access-portal",
        "aud": "linux-access-portal-api",
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            audience="linux-access-portal-api",
            issuer="linux-access-portal",
        )
        return payload
    except JWTError:
        return None


def generate_request_id() -> str:
    """Generate a unique request ID."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_part = secrets.token_hex(4).upper()
    return f"LAR-{timestamp}-{random_part}"


def generate_csrf_token() -> str:
    """Generate a CSRF token."""
    return secrets.token_urlsafe(32)
