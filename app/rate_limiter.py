"""
Rate limiting service for API endpoints.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, status

from app.database import db_manager
from app.config import settings

logger = logging.getLogger(__name__)


class RateLimitService:
    """Service for handling API rate limiting."""

    def __init__(self):
        """Initialize rate limiting service with configuration."""
        # Default rate limiting configuration
        self.max_requests = getattr(settings, 'rate_limit_max_requests', 3)
        self.window_hours = getattr(settings, 'rate_limit_window_hours', 3)
        self.window_seconds = self.window_hours * 3600

    async def check_rate_limit(self, ip_address: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if an IP address is within rate limits.
        
        Args:
            ip_address: The client's IP address
            
        Returns:
            Tuple of (is_allowed, rate_limit_info)
            - is_allowed: True if request is allowed, False if rate limited
            - rate_limit_info: Dict containing remaining requests, reset time, etc.
        """
        try:
            # Get existing rate limit record
            record = await db_manager.get_rate_limit_record(ip_address)
            now = datetime.now()

            if not record:
                # First request from this IP - create new record
                await db_manager.create_rate_limit_record(ip_address)
                return True, {
                    "remaining_requests": self.max_requests - 1,
                    "window_reset_time": now + timedelta(seconds=self.window_seconds),
                    "request_count": 1
                }

            # Parse existing record
            window_start = datetime.fromisoformat(record["window_start"].replace('Z', '+00:00'))
            request_count = record["request_count"]
            last_request_time = datetime.fromisoformat(record["last_request_time"].replace('Z', '+00:00'))

            # Check if we're still within the current window
            time_since_window_start = (now - window_start).total_seconds()

            if time_since_window_start >= self.window_seconds:
                # Window has expired - reset the counter
                await db_manager.reset_rate_limit_window(ip_address)
                return True, {
                    "remaining_requests": self.max_requests - 1,
                    "window_reset_time": now + timedelta(seconds=self.window_seconds),
                    "request_count": 1
                }

            # Check if we've exceeded the rate limit
            if request_count >= self.max_requests:
                # Rate limit exceeded
                time_until_reset = self.window_seconds - time_since_window_start
                return False, {
                    "remaining_requests": 0,
                    "window_reset_time": window_start + timedelta(seconds=self.window_seconds),
                    "request_count": request_count,
                    "retry_after_seconds": int(time_until_reset)
                }

            # Increment the request count
            new_request_count = request_count + 1
            await db_manager.update_rate_limit_record(
                ip_address, 
                new_request_count, 
                window_start, 
                now
            )

            return True, {
                "remaining_requests": self.max_requests - new_request_count,
                "window_reset_time": window_start + timedelta(seconds=self.window_seconds),
                "request_count": new_request_count
            }

        except Exception as e:
            logger.error(f"Error checking rate limit for IP {ip_address}: {e}")
            # In case of error, allow the request but log the issue
            return True, {
                "remaining_requests": self.max_requests - 1,
                "window_reset_time": datetime.now() + timedelta(seconds=self.window_seconds),
                "request_count": 1,
                "error": "Rate limit check failed, allowing request"
            }

    async def get_rate_limit_info(self, ip_address: str) -> Dict[str, Any]:
        """
        Get current rate limit information for an IP address without incrementing the counter.
        
        Args:
            ip_address: The client's IP address
            
        Returns:
            Dict containing rate limit information
        """
        try:
            record = await db_manager.get_rate_limit_record(ip_address)
            now = datetime.now()

            if not record:
                return {
                    "remaining_requests": self.max_requests,
                    "window_reset_time": None,
                    "request_count": 0
                }

            # Parse existing record
            window_start = datetime.fromisoformat(record["window_start"].replace('Z', '+00:00'))
            request_count = record["request_count"]

            # Check if we're still within the current window
            time_since_window_start = (now - window_start).total_seconds()

            if time_since_window_start >= self.window_seconds:
                # Window has expired
                return {
                    "remaining_requests": self.max_requests,
                    "window_reset_time": None,
                    "request_count": 0
                }

            # Still within window
            return {
                "remaining_requests": max(0, self.max_requests - request_count),
                "window_reset_time": window_start + timedelta(seconds=self.window_seconds),
                "request_count": request_count
            }

        except Exception as e:
            logger.error(f"Error getting rate limit info for IP {ip_address}: {e}")
            return {
                "remaining_requests": self.max_requests,
                "window_reset_time": None,
                "request_count": 0,
                "error": "Failed to get rate limit info"
            }

    async def cleanup_expired_records(self) -> int:
        """
        Clean up expired rate limit records.
        
        Returns:
            Number of records cleaned up
        """
        try:
            # Clean up records older than 24 hours
            return await db_manager.cleanup_expired_rate_limits(hours_old=24)
        except Exception as e:
            logger.error(f"Error cleaning up expired rate limit records: {e}")
            return 0

    def extract_ip_address(self, request) -> str:
        """
        Extract the real IP address from request headers.
        Handles proxy/load balancer scenarios.
        
        Args:
            request: FastAPI request object
            
        Returns:
            IP address string
        """
        # Check for forwarded IP (from proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs, take the first one
            return forwarded_for.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fallback to direct client IP
        if hasattr(request, 'client') and request.client:
            return request.client.host

        # Last resort fallback
        return "127.0.0.1"


# Global rate limit service instance
rate_limit_service = RateLimitService()
