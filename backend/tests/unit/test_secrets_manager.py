"""
Unit tests for the Secrets Manager module.
Tests cache behavior, enable/disable logic, SSH key retrieval.
"""

import os
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.core.secrets_manager import (
    is_secrets_manager_enabled,
    validate_sensitive_keys_present,
    create_secret_template,
    get_ssh_key_from_secrets_manager,
    invalidate_ssh_key_cache,
    _sm_cache,
    _sm_cache_times,
    _SM_CACHE_TTL_SECONDS,
    SENSITIVE_KEYS,
)


class TestSecretsManagerEnabled:
    """Test enable/disable logic."""

    def test_disabled_by_default(self):
        """Secrets Manager should be disabled when env var is not set."""
        with patch.dict(os.environ, {"AWS_SECRETS_MANAGER_ENABLED": "false"}):
            assert is_secrets_manager_enabled() is False

    def test_enabled_with_true(self):
        """Should be enabled when set to 'true'."""
        with patch.dict(os.environ, {"AWS_SECRETS_MANAGER_ENABLED": "true"}):
            assert is_secrets_manager_enabled() is True

    def test_enabled_with_yes(self):
        """Should be enabled when set to 'yes'."""
        with patch.dict(os.environ, {"AWS_SECRETS_MANAGER_ENABLED": "yes"}):
            assert is_secrets_manager_enabled() is True

    def test_enabled_with_1(self):
        """Should be enabled when set to '1'."""
        with patch.dict(os.environ, {"AWS_SECRETS_MANAGER_ENABLED": "1"}):
            assert is_secrets_manager_enabled() is True

    def test_disabled_with_random_value(self):
        """Should be disabled for random/invalid values."""
        with patch.dict(os.environ, {"AWS_SECRETS_MANAGER_ENABLED": "maybe"}):
            assert is_secrets_manager_enabled() is False

    def test_case_insensitive(self):
        """Check should be case-insensitive."""
        with patch.dict(os.environ, {"AWS_SECRETS_MANAGER_ENABLED": "TRUE"}):
            assert is_secrets_manager_enabled() is True


class TestValidateSensitiveKeys:
    """Test sensitive key validation."""

    def test_all_keys_present(self):
        """No missing keys when all are set."""
        env = {key: "some-value" for key in SENSITIVE_KEYS}
        with patch.dict(os.environ, env, clear=False):
            missing = validate_sensitive_keys_present()
            assert len(missing) == 0

    def test_missing_keys_detected(self):
        """Should detect missing sensitive keys."""
        env = {key: "" for key in SENSITIVE_KEYS}
        with patch.dict(os.environ, env):
            missing = validate_sensitive_keys_present()
            assert len(missing) == len(SENSITIVE_KEYS)

    def test_partial_keys_missing(self):
        """Should detect partially missing keys."""
        env = {"SECRET_KEY": "present", "SESSION_SECRET_KEY": "present"}
        with patch.dict(os.environ, env, clear=False):
            # Clear other keys that might interfere
            for key in SENSITIVE_KEYS:
                if key not in env:
                    os.environ.pop(key, None)
            missing = validate_sensitive_keys_present()
            # Should have some missing (those not in env)
            assert "SECRET_KEY" not in missing
            assert "SESSION_SECRET_KEY" not in missing


class TestSecretTemplate:
    """Test secret template generation."""

    def test_template_is_valid_json(self):
        """Template should be valid JSON."""
        template = create_secret_template()
        parsed = json.loads(template)
        assert isinstance(parsed, dict)

    def test_template_has_required_keys(self):
        """Template should have all sensitive keys."""
        template = create_secret_template()
        parsed = json.loads(template)
        for key in SENSITIVE_KEYS:
            assert key in parsed

    def test_template_values_are_non_empty(self):
        """Template values should be non-empty placeholders."""
        template = create_secret_template()
        parsed = json.loads(template)
        for key, value in parsed.items():
            assert value is not None
            assert len(value) > 0


class TestSSHKeyFromSecretsManager:
    """Test SSH key retrieval from Secrets Manager (mocked)."""

    def test_returns_none_when_disabled(self):
        """Should return None when SM is disabled."""
        with patch.dict(os.environ, {"AWS_SECRETS_MANAGER_ENABLED": "false"}):
            result = get_ssh_key_from_secrets_manager("default")
            assert result is None

    def test_cache_hit_returns_cached_value(self):
        """Should return cached value without calling AWS."""
        cache_key = "ssh_key:test-key"
        test_data = {"private_key": "cached-key", "passphrase": "", "key_type": "rsa"}

        # Manually populate cache
        _sm_cache[cache_key] = test_data
        _sm_cache_times[cache_key] = datetime.now()

        with patch.dict(os.environ, {"AWS_SECRETS_MANAGER_ENABLED": "true"}):
            result = get_ssh_key_from_secrets_manager("test-key")
            assert result == test_data

        # Cleanup
        _sm_cache.pop(cache_key, None)
        _sm_cache_times.pop(cache_key, None)

    def test_cache_expired_fetches_from_aws(self):
        """Should fetch from AWS when cache is expired."""
        cache_key = "ssh_key:expired-key"
        _sm_cache[cache_key] = {"private_key": "old", "passphrase": "", "key_type": "rsa"}
        _sm_cache_times[cache_key] = datetime.now() - timedelta(seconds=_SM_CACHE_TTL_SECONDS + 100)

        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({
                "expired-key": {
                    "private_key": "new-key-content",
                    "passphrase": "pass",
                    "key_type": "ecdsa",
                }
            })
        }
        mock_session = MagicMock()
        mock_session.client.return_value = mock_client

        with patch.dict(os.environ, {"AWS_SECRETS_MANAGER_ENABLED": "true"}):
            with patch("boto3.Session", return_value=mock_session):
                result = get_ssh_key_from_secrets_manager("expired-key")
                assert result is not None
                assert result["private_key"] == "new-key-content"
                assert result["key_type"] == "ecdsa"

        # Cleanup
        _sm_cache.pop(cache_key, None)
        _sm_cache_times.pop(cache_key, None)


class TestSSHKeyCacheInvalidation:
    """Test cache invalidation."""

    def test_invalidate_specific_key(self):
        """Should invalidate a specific SSH key cache entry."""
        cache_key = "ssh_key:my-key"
        _sm_cache[cache_key] = {"private_key": "data"}
        _sm_cache_times[cache_key] = datetime.now()

        invalidate_ssh_key_cache("my-key")

        assert cache_key not in _sm_cache
        assert cache_key not in _sm_cache_times

    def test_invalidate_all_ssh_keys(self):
        """Should invalidate all SSH key cache entries."""
        _sm_cache["ssh_key:key1"] = {"private_key": "d1"}
        _sm_cache["ssh_key:key2"] = {"private_key": "d2"}
        _sm_cache_times["ssh_key:key1"] = datetime.now()
        _sm_cache_times["ssh_key:key2"] = datetime.now()
        # Non-SSH key should remain
        _sm_cache["other:data"] = "keep"

        invalidate_ssh_key_cache(None)

        assert "ssh_key:key1" not in _sm_cache
        assert "ssh_key:key2" not in _sm_cache
        assert _sm_cache.get("other:data") == "keep"

        # Cleanup
        _sm_cache.pop("other:data", None)

    def test_invalidate_nonexistent_key_no_error(self):
        """Should not raise error when invalidating non-existent key."""
        invalidate_ssh_key_cache("nonexistent-key")
        # Should not raise
