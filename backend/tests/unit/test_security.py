"""Unit tests for security utilities."""

from datetime import UTC, datetime, timedelta

from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, verify_password


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_get_password_hash(self) -> None:
        """Test password hashing creates valid bcrypt hash."""
        password = "test_password_123"
        hashed = get_password_hash(password)

        # Bcrypt hashes start with $2b$
        assert hashed.startswith("$2b$")
        # Hash should not be the same as plaintext
        assert hashed != password
        # Hash should be approximately 60 characters
        assert len(hashed) >= 59

    def test_password_hash_is_random(self) -> None:
        """Test same password produces different hashes (due to salt)."""
        password = "test_password_123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        # Same password should produce different hashes
        assert hash1 != hash2

    def test_verify_password_correct(self) -> None:
        """Test password verification succeeds with correct password."""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """Test password verification fails with incorrect password."""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_case_sensitive(self) -> None:
        """Test password verification is case-sensitive."""
        password = "TestPassword"
        hashed = get_password_hash(password)

        assert verify_password("testpassword", hashed) is False


class TestJWTTokens:
    """Test JWT token creation and validation."""

    def test_create_access_token(self) -> None:
        """Test JWT token creation with default expiration."""
        subject = "test_user@example.com"
        token = create_access_token(subject)

        # Decode token (don't verify for test)
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        assert decoded["sub"] == subject
        assert "exp" in decoded

    def test_create_access_token_with_custom_expiry(self) -> None:
        """Test JWT token creation with custom expiration."""
        subject = "test_user@example.com"
        expires_delta = timedelta(hours=1)
        token = create_access_token(subject, expires_delta=expires_delta)

        # Decode token
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        # Check expiration is approximately 1 hour from now
        exp_timestamp = decoded["exp"]
        expected_exp = datetime.now(UTC) + expires_delta
        actual_exp = datetime.fromtimestamp(exp_timestamp, UTC)

        # Allow 5 second tolerance for test execution time
        time_diff = abs((expected_exp - actual_exp).total_seconds())
        assert time_diff < 5

    def test_create_access_token_with_integer_subject(self) -> None:
        """Test JWT token creation with integer subject (user ID)."""
        subject = 12345
        token = create_access_token(subject)

        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        # Subject should be converted to string
        assert decoded["sub"] == "12345"

    def test_jwt_token_is_valid_format(self) -> None:
        """Test JWT token has correct format (3 parts separated by dots)."""
        token = create_access_token("test_subject")

        # JWT tokens have 3 parts: header.payload.signature
        parts = token.split(".")
        assert len(parts) == 3

        # Each part should be non-empty
        assert all(len(part) > 0 for part in parts)
