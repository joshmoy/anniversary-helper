"""
Tests for password hashing and verification functionality.
"""
import pytest
import os
from app.auth import AuthenticationService


class TestPasswordHashing:
    """Test password hashing and verification functionality."""

    def test_get_password_hash_returns_bcrypt_hash(self):
        """Test that get_password_hash returns a bcrypt hash."""
        password = "test_password_123"
        hashed = AuthenticationService.get_password_hash(password)
        
        # Should start with $2b$ (bcrypt identifier)
        assert hashed.startswith("$2b$")
        # Should be a reasonable length for bcrypt
        assert len(hashed) >= 50
        # Should not be the same as the original password
        assert hashed != password

    def test_verify_password_correct_password(self):
        """Test that verify_password returns True for correct password."""
        password = "test_password_123"
        hashed = AuthenticationService.get_password_hash(password)
        
        # Should verify correctly
        assert AuthenticationService.verify_password(password, hashed) is True

    def test_verify_password_wrong_password(self):
        """Test that verify_password returns False for wrong password."""
        password = "test_password_123"
        wrong_password = "wrong_password_456"
        hashed = AuthenticationService.get_password_hash(password)
        
        # Should not verify with wrong password
        assert AuthenticationService.verify_password(wrong_password, hashed) is False

    def test_verify_password_empty_password(self):
        """Test that verify_password handles empty password correctly."""
        password = "test_password_123"
        hashed = AuthenticationService.get_password_hash(password)
        
        # Should not verify with empty password
        assert AuthenticationService.verify_password("", hashed) is False

    def test_verify_password_none_password(self):
        """Test that verify_password handles None password correctly."""
        password = "test_password_123"
        hashed = AuthenticationService.get_password_hash(password)
        
        # Should not verify with None password
        assert AuthenticationService.verify_password(None, hashed) is False

    def test_verify_password_invalid_hash(self):
        """Test that verify_password handles invalid hash gracefully."""
        password = "test_password_123"
        invalid_hash = "invalid_hash_string"
        
        # Should return False for invalid hash
        assert AuthenticationService.verify_password(password, invalid_hash) is False

    def test_password_hash_consistency(self):
        """Test that the same password produces different hashes (salt)."""
        password = "test_password_123"
        hash1 = AuthenticationService.get_password_hash(password)
        hash2 = AuthenticationService.get_password_hash(password)
        
        # Hashes should be different due to salt
        assert hash1 != hash2
        
        # But both should verify correctly
        assert AuthenticationService.verify_password(password, hash1) is True
        assert AuthenticationService.verify_password(password, hash2) is True

    def test_existing_bcrypt_hash_compatibility(self):
        """Test compatibility with existing bcrypt hashes."""
        # Generate a real bcrypt hash for testing
        password = "test123"
        existing_hash = AuthenticationService.get_password_hash(password)
        
        # Should verify correctly with existing hash
        assert AuthenticationService.verify_password(password, existing_hash) is True
        
        # Should not verify with wrong password
        assert AuthenticationService.verify_password("wrong", existing_hash) is False

    def test_unicode_password_handling(self):
        """Test that unicode passwords are handled correctly."""
        password = "测试密码_123_🔐"
        hashed = AuthenticationService.get_password_hash(password)
        
        # Should verify correctly
        assert AuthenticationService.verify_password(password, hashed) is True
        
        # Should not verify with wrong unicode password
        wrong_password = "测试密码_456_🔒"
        assert AuthenticationService.verify_password(wrong_password, hashed) is False

    def test_long_password_handling(self):
        """Test that long passwords are handled correctly."""
        # bcrypt has a 72-byte limit, so test with a password that's exactly 72 bytes
        password = "a" * 72  # 72-byte password (bcrypt limit)
        hashed = AuthenticationService.get_password_hash(password)
        
        # Should verify correctly
        assert AuthenticationService.verify_password(password, hashed) is True
        
        # Should not verify with truncated password
        truncated_password = password[:-1]
        assert AuthenticationService.verify_password(truncated_password, hashed) is False

    def test_get_password_hash_error_handling(self):
        """Test that get_password_hash raises HTTPException on error."""
        # This test is more about ensuring the error handling is in place
        # In practice, bcrypt should not fail with normal inputs
        try:
            # Test with a very long password that might cause issues
            very_long_password = "a" * 10000
            hashed = AuthenticationService.get_password_hash(very_long_password)
            # If it doesn't raise an exception, that's fine too
            assert isinstance(hashed, str)
        except Exception as e:
            # If an exception is raised, it should be an HTTPException
            from fastapi import HTTPException
            assert isinstance(e, HTTPException)
            assert e.status_code == 500

    def test_verify_password_error_handling(self):
        """Test that verify_password returns False on error."""
        # Test with malformed hash
        malformed_hash = "$2b$invalid"
        result = AuthenticationService.verify_password("test", malformed_hash)
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__])
