"""
CareerBuddy - Rate Limiting Middleware
Rate limiting middleware to prevent abuse
Author: Sir Dave
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Tuple
import time


class RateLimiter:
    """
    Simple in-memory rate limiter
    In production, use Redis for distributed rate limiting
    """
    
    def __init__(self, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        
        # Store: {identifier: [(timestamp, count), ...]}
        self.minute_buckets: Dict[str, list] = defaultdict(list)
        self.hour_buckets: Dict[str, list] = defaultdict(list)
    
    def _clean_old_entries(self, buckets: dict, max_age_seconds: int):
        """Remove entries older than max_age_seconds"""
        now = time.time()
        for key in list(buckets.keys()):
            buckets[key] = [
                (ts, count) for ts, count in buckets[key]
                if now - ts < max_age_seconds
            ]
            if not buckets[key]:
                del buckets[key]
    
    def check_rate_limit(self, identifier: str) -> Tuple[bool, str]:
        """
        Check if request should be allowed
        
        Args:
            identifier: User identifier (IP, user_id, etc.)
        
        Returns:
            (allowed, reason) tuple
        """
        now = time.time()
        
        # Clean old entries periodically
        self._clean_old_entries(self.minute_buckets, 60)
        self._clean_old_entries(self.hour_buckets, 3600)
        
        # Check minute limit
        minute_requests = sum(count for ts, count in self.minute_buckets[identifier])
        if minute_requests >= self.requests_per_minute:
            return False, f"Rate limit exceeded: {self.requests_per_minute} requests per minute"
        
        # Check hour limit
        hour_requests = sum(count for ts, count in self.hour_buckets[identifier])
        if hour_requests >= self.requests_per_hour:
            return False, f"Rate limit exceeded: {self.requests_per_hour} requests per hour"
        
        # Record this request
        self.minute_buckets[identifier].append((now, 1))
        self.hour_buckets[identifier].append((now, 1))
        
        return True, ""


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting"""
    
    def __init__(self, app, rate_limiter: RateLimiter):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        
        # Endpoints to exclude from rate limiting
        self.excluded_paths = {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json"
        }
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)
        
        # Get identifier (IP address or user ID from headers)
        identifier = request.client.host if request.client else "unknown"
        
        # Check rate limit
        allowed, reason = self.rate_limiter.check_rate_limit(identifier)
        
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": reason,
                    "retry_after": "60 seconds"
                }
            )
        
        # Process request
        response = await call_next(request)
        return response


# Global rate limiter instance
rate_limiter = RateLimiter(
    requests_per_minute=60,  # 60 requests per minute
    requests_per_hour=1000    # 1000 requests per hour
)
