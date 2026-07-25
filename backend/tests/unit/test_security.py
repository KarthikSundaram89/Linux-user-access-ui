"""
Unit tests for the security module.
Tests JWT creation/validation (with aud/iss), password hashing, Fernet encryption, CSRF token.
"""

import pytest
from datetime import timedelta, datetime, timezone
from unittest.mock import patch

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
    encrypt_value,
    decrypt_value,
    generate_request_id,
    generate_csrf_token,
    get_fernet,
)


class TestJWTTokens:
    """Test JWT token creation and validation."""

    def test_create_access_token_returns_string(self):
        """Token should be a non-empty string."""
        token = create_access_token({"sub": "1", "email": "user@test.com"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self):
        """Valid token should decode correctly."""
        data = {"sub": "42", "email": "user@company.com"}
        token = create_access_token(data)
        payload = decode_access_token(token)

        assert payload is not None
        assert payload["sub"] == "42"
        assert payload["email"] == "user@company.com"

    def test_token_has_issuer(self):
        """Token should contain iss claim."""
        token = create_access_token({"sub": "1", "email": "user@test.com"})
        payload = decode_access_token(token)
        assert payload["iss"] == "linux-access-portal"

    def test_token_has_audience(self):
        """Token should contain aud claim."""
        token = create_access_token({"sub": "1", "email": "user@test.com"})
        payload = decode_access_token(token)
        assert payload["aud"] == "linux-access-portal-api"

    def test_token_has_expiry(self):
        """Token should have an exp claim in the future."""
        token = create_access_token({"sub": "1", "email": "user@test.com"})
        payload = decode_access_token(token)
        assert "exp" in payload
        assert payload["exp"] > datetime.now(timezone.utc).timestamp()

    def test_custom_expiry_delta(self):
        """Token with custom expiry should respect the delta."""
        delta = timedelta(minutes=5)
        token = create_access_token({"sub": "1", "email": "user@test.com"}, expires_delta=delta)
        payload = decode_access_token(token)
        assert payload is not None
        # Should expire within ~5 min from now
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        assert (exp_time - now).total_seconds() <= 300 + 5  # 5 sec tolerance

    def test_decode_invalid_token_returns_none(self):
        """Invalid token should return None."""
        result = decode_access_token("invalid.token.here")
        assert result is None

    def test_decode_tampered_token_returns_none(self):
        """Tampered token should return None."""
        token = create_access_token({"sub": "1", "email": "user@test.com"})
        # Tamper with the token
        tampered = token[:-5] + "XXXXX"
        result = decode_access_token(tampered)
        assert result is None

    def test_decode_empty_token_returns_none(self):
        """Empty token should return None."""
        result = decode_access_token("")
        assert result is None

    def test_expired_token_returns_none(self):
        """Expired token should return None."""
        token = create_access_token(
            {"sub": "1", "email": "user@test.com"},
            expires_delta=timedelta(seconds=-10),
        )
        result = decode_access_token(token)
        assert result is None


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password_returns_string(self):
        """Hashed password should be a non-empty string."""
        hashed = hash_password("mypassword123")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_different_from_plain(self):
        """Hash should differ from plaintext."""
        plain = "mypassword123"
        hashed = hash_password(plain)
        assert hashed != plain

    def test_verify_password_correct(self):
        """Correct password should verify."""
        plain = "SuperSecure!123"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_password_incorrect(self):
        """Incorrect password should not verify."""
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_hash_is_unique_each_time(self):
        """Same password should produce different hashes (bcrypt salt)."""
        plain = "mypassword123"
        hash1 = hash_password(plain)
        hash2 = hash_password(plain)
        assert hash1 != hash2  # Different salts
        # But both should verify
        assert verify_password(plain, hash1) is True
        assert verify_password(plain, hash2) is True


class TestFernetEncryption:
    """Test Fernet encryption/decryption for sensitive data."""

    def test_encrypt_returns_string(self):
        """Encrypted value should be a non-empty string."""
        encrypted = encrypt_value("sensitive data")
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0

    def test_encrypt_differs_from_plain(self):
        """Encrypted value should differ from plaintext."""
        plain = "my secret value"
        encrypted = encrypt_value(plain)
        assert encrypted != plain

    def test_decrypt_returns_original(self):
        """Decrypted value should match original plaintext."""
        plain = "SSH private key content here"
        encrypted = encrypt_value(plain)
        decrypted = decrypt_value(encrypted)
        assert decrypted == plain

    def test_encrypt_decrypt_empty_string(self):
        """Empty string should encrypt and decrypt correctly."""
        encrypted = encrypt_value("")
        decrypted = decrypt_value(encrypted)
        assert decrypted == ""

    def test_encrypt_decrypt_special_characters(self):
        """Special characters should survive encrypt/decrypt."""
        plain = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpA....\n-----END RSA PRIVATE KEY-----"
        encrypted = encrypt_value(plain)
        decrypted = decrypt_value(encrypted)
        assert decrypted == plain

    def test_decrypt_invalid_data_raises(self):
        """Decrypting invalid data should raise an exception."""
        with pytest.raises(Exception):
            decrypt_value("not-a-valid-fernet-token")

    def test_get_fernet_returns_consistent_instance(self):
        """get_fernet should return the same key on repeated calls."""
        f1 = get_fernet()
        f2 = get_fernet()
        # They should be the same object (cached)
        assert f1 is f2


class TestRequestIdGeneration:
    """Test request ID generation."""

    def test_request_id_format(self):
        """Request ID should match LAR-YYYYMMDD-XXXXXXXX format."""
        req_id = generate_request_id()
        assert req_id.startswith("LAR-")
        parts = req_id.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 8  # 4 hex bytes = 8 chars

    def test_request_ids_are_unique(self):
        """Multiple IDs should be unique."""
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100


class TestCSRFToken:
    """Test CSRF token generation."""

    def test_csrf_token_is_string(self):
        """CSRF token should be a non-empty string."""
        token = generate_csrf_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_csrf_tokens_are_unique(self):
        """Multiple CSRF tokens should be unique."""
        tokens = {generate_csrf_token() for _ in range(50)}
        assert len(tokens) == 50

    def test_csrf_token_length(self):
        """CSRF token should be URL-safe base64, at least 32 bytes encoded."""
        token = generate_csrf_token()
        # token_urlsafe(32) produces ~43 characters
        assert len(token) >= 40
