"""
Tests for the Anniversary Wish API endpoints.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app
from app.models import AnniversaryWishRequest, AnniversaryType, ToneType
from app.rate_limiter import rate_limit_service
from app.ai_wish_generator import ai_wish_generator

client = TestClient(app)


class TestAnniversaryWishAPI:
    """Test cases for the Anniversary Wish API."""

    def test_generate_anniversary_wish_success(self):
        """Test successful anniversary wish generation."""
        with patch.object(rate_limit_service, 'extract_ip_address', return_value='127.0.0.1'), \
             patch.object(rate_limit_service, 'check_rate_limit', return_value=(True, {
                 'remaining_requests': 2,
                 'window_reset_time': datetime.now() + timedelta(hours=3),
                 'request_count': 1
             })), \
             patch.object(ai_wish_generator, 'generate_anniversary_wish', return_value="Test wish message"):
            
            request_data = {
                "name": "John and Sarah",
                "anniversary_type": "wedding-anniversary",
                "relationship": "friend",
                "tone": "warm",
                "context": "Test context"
            }
            
            response = client.post("/api/anniversary-wish", json=request_data)
            
            assert response.status_code == 200
            data = response.json()
            assert "generated_wish" in data
            assert "request_id" in data
            assert "remaining_requests" in data
            assert data["generated_wish"] == "Test wish message"
            assert data["remaining_requests"] == 2

    def test_generate_anniversary_wish_rate_limited(self):
        """Test rate limiting for non-authenticated users."""
        with patch.object(rate_limit_service, 'extract_ip_address', return_value='127.0.0.1'), \
             patch.object(rate_limit_service, 'check_rate_limit', return_value=(False, {
                 'remaining_requests': 0,
                 'window_reset_time': datetime.now() + timedelta(hours=2),
                 'request_count': 3,
                 'retry_after_seconds': 7200
             })):
            
            request_data = {
                "name": "John and Sarah",
                "anniversary_type": "wedding-anniversary",
                "relationship": "friend",
                "tone": "warm"
            }
            
            response = client.post("/api/anniversary-wish", json=request_data)
            
            assert response.status_code == 429
            assert "Rate limit exceeded" in response.json()["detail"]
            assert "Retry-After" in response.headers

    def test_generate_anniversary_wish_validation_error(self):
        """Test validation error for invalid request data."""
        request_data = {
            "name": "",  # Invalid: empty name
            "anniversary_type": "wedding-anniversary",
            "relationship": "friend",
            "tone": "warm"
        }
        
        response = client.post("/api/anniversary-wish", json=request_data)
        
        assert response.status_code == 422

    def test_get_rate_limit_info(self):
        """Test rate limit info endpoint."""
        with patch.object(rate_limit_service, 'extract_ip_address', return_value='127.0.0.1'), \
             patch.object(rate_limit_service, 'get_rate_limit_info', return_value={
                 'remaining_requests': 2,
                 'window_reset_time': datetime.now() + timedelta(hours=3),
                 'request_count': 1
             }):
            
            response = client.get("/api/anniversary-wish/rate-limit-info")
            
            assert response.status_code == 200
            data = response.json()
            assert "ip_address" in data
            assert "is_authenticated" in data
            assert "rate_limit_info" in data
            assert data["ip_address"] == "127.0.0.1"
            assert data["is_authenticated"] is False

    def test_anniversary_wish_request_validation(self):
        """Test AnniversaryWishRequest model validation."""
        # Valid request
        valid_request = AnniversaryWishRequest(
            name="John and Sarah",
            anniversary_type=AnniversaryType.WEDDING_ANNIVERSARY,
            relationship="friend",
            tone=ToneType.WARM,
            context="Test context"
        )
        assert valid_request.name == "John and Sarah"
        assert valid_request.anniversary_type == AnniversaryType.WEDDING_ANNIVERSARY
        assert valid_request.relationship == "friend"
        assert valid_request.tone == ToneType.WARM

        # Test with minimal required fields
        minimal_request = AnniversaryWishRequest(
            name="John",
            anniversary_type=AnniversaryType.WORK_ANNIVERSARY,
            relationship="colleague"
        )
        assert minimal_request.name == "John"
        assert minimal_request.relationship == "colleague"
        assert minimal_request.tone == ToneType.WARM  # Default tone
        assert minimal_request.context is None


class TestRateLimitService:
    """Test cases for the RateLimitService."""

    @pytest.mark.asyncio
    async def test_check_rate_limit_new_ip(self):
        """Test rate limit check for new IP address."""
        from app.database import db_manager
        
        with patch.object(db_manager, 'get_rate_limit_record', return_value=None), \
             patch.object(db_manager, 'create_rate_limit_record', return_value={}):
            
            is_allowed, rate_info = await rate_limit_service.check_rate_limit("192.168.1.1")
            
            assert is_allowed is True
            assert rate_info["remaining_requests"] == 2  # 3 - 1

    @pytest.mark.asyncio
    async def test_check_rate_limit_existing_ip_within_limit(self):
        """Test rate limit check for existing IP within limit."""
        mock_record = {
            "ip_address": "192.168.1.1",
            "request_count": 1,
            "window_start": datetime.now().isoformat(),
            "last_request_time": datetime.now().isoformat()
        }
        
        from app.database import db_manager
        
        with patch.object(db_manager, 'get_rate_limit_record', return_value=mock_record), \
             patch.object(db_manager, 'update_rate_limit_record', return_value=True):
            
            is_allowed, rate_info = await rate_limit_service.check_rate_limit("192.168.1.1")
            
            assert is_allowed is True
            assert rate_info["remaining_requests"] == 1  # 3 - 2

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self):
        """Test rate limit check when limit is exceeded."""
        mock_record = {
            "ip_address": "192.168.1.1",
            "request_count": 3,
            "window_start": datetime.now().isoformat(),
            "last_request_time": datetime.now().isoformat()
        }
        
        from app.database import db_manager
        
        with patch.object(db_manager, 'get_rate_limit_record', return_value=mock_record):
            
            is_allowed, rate_info = await rate_limit_service.check_rate_limit("192.168.1.1")
            
            assert is_allowed is False
            assert rate_info["remaining_requests"] == 0
            assert "retry_after_seconds" in rate_info


class TestAIWishGenerator:
    """Test cases for the AIWishGenerator."""

    def test_get_relationship_context(self):
        """Test relationship context generation."""
        from app.ai_wish_generator import AIWishGenerator
        
        generator = AIWishGenerator()
        
        assert generator.get_relationship_context("spouse") == "as their loving spouse"
        assert generator.get_relationship_context("friend") == "as their dear friend"
        assert generator.get_relationship_context("colleague") == "as their colleague"
        assert generator.get_relationship_context("best friend") == "as their dear friend"
        assert generator.get_relationship_context("custom relationship") == "as their custom relationship"

    def test_get_anniversary_type_context(self):
        """Test anniversary type context generation."""
        from app.ai_wish_generator import AIWishGenerator
        
        generator = AIWishGenerator()
        
        assert generator.get_anniversary_type_context(AnniversaryType.WEDDING_ANNIVERSARY) == "wedding anniversary"
        assert generator.get_anniversary_type_context(AnniversaryType.WORK_ANNIVERSARY) == "work anniversary"
        assert generator.get_anniversary_type_context(AnniversaryType.BIRTHDAY) == "birthday"
        assert generator.get_anniversary_type_context(AnniversaryType.PROMOTION) == "promotion celebration"
        assert generator.get_anniversary_type_context(AnniversaryType.RETIREMENT) == "retirement celebration"

    def test_get_tone_instructions(self):
        """Test tone instruction generation."""
        from app.ai_wish_generator import AIWishGenerator
        
        generator = AIWishGenerator()
        
        assert "professional" in generator.get_tone_instructions(ToneType.PROFESSIONAL).lower()
        assert "friendly" in generator.get_tone_instructions(ToneType.FRIENDLY).lower()
        assert "warm" in generator.get_tone_instructions(ToneType.WARM).lower()
        assert "humorous" in generator.get_tone_instructions(ToneType.HUMOROUS).lower()
        assert "formal" in generator.get_tone_instructions(ToneType.FORMAL).lower()

    def test_generate_fallback_wish(self):
        """Test fallback wish generation."""
        from app.ai_wish_generator import AIWishGenerator
        
        generator = AIWishGenerator()
        
        request = AnniversaryWishRequest(
            name="John and Sarah",
            anniversary_type=AnniversaryType.WEDDING_ANNIVERSARY,
            relationship="friend",
            tone=ToneType.WARM
        )
        
        wish = generator.generate_fallback_wish(request)
        
        assert "John and Sarah" in wish
        assert "Wedding Anniversary" in wish
        # Should contain inspirational content but not Bible verses
        assert len(wish) > 50  # Should be a substantial message

    def test_clean_ai_message(self):
        """Test AI message cleaning."""
        from app.ai_wish_generator import AIWishGenerator
        
        generator = AIWishGenerator()
        
        # Test message with unwanted introductory text
        dirty_message = "Here is a warm anniversary wish for John and Sarah: Happy Anniversary! Here's to many more moments worth celebrating."
        clean_message = generator._clean_ai_message(dirty_message)
        
        assert "Here is a warm" not in clean_message
        assert "Happy Anniversary!" in clean_message
        assert "moments worth celebrating" in clean_message


if __name__ == "__main__":
    pytest.main([__file__])
