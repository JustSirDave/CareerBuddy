"""
CareerBuddy - Error Monitoring Service
Tracks errors, exceptions, and critical events
Author: Sir Dave
"""
from loguru import logger
from datetime import datetime
from typing import Optional
import traceback
import json


class ErrorMonitor:
    """Monitor and log application errors"""
    
    @staticmethod
    def log_error(
        error: Exception,
        context: str,
        user_id: Optional[str] = None,
        additional_data: Optional[dict] = None
    ):
        """
        Log an error with context and metadata
        
        Args:
            error: The exception that occurred
            context: Where the error happened (e.g., "webhook", "document_generation")
            user_id: User ID if available
            additional_data: Any additional context data
        """
        error_data = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
            "user_id": user_id,
            "traceback": traceback.format_exc(),
            "additional_data": additional_data or {}
        }
        
        logger.error(f"[ERROR_MONITOR] {context}: {error_data}")
        
        # In production, you could send this to:
        # - Sentry
        # - CloudWatch
        # - DataDog
        # - Custom error tracking service
        
        return error_data
    
    @staticmethod
    def log_critical(
        message: str,
        context: str,
        user_id: Optional[str] = None,
        additional_data: Optional[dict] = None
    ):
        """
        Log a critical event (not necessarily an error)
        
        Args:
            message: The critical event message
            context: Where it happened
            user_id: User ID if available
            additional_data: Any additional context
        """
        critical_data = {
            "timestamp": datetime.now().isoformat(),
            "level": "CRITICAL",
            "message": message,
            "context": context,
            "user_id": user_id,
            "additional_data": additional_data or {}
        }
        
        logger.critical(f"[CRITICAL] {context}: {critical_data}")
        
        return critical_data
    
    @staticmethod
    def log_performance(
        operation: str,
        duration_ms: float,
        context: str,
        user_id: Optional[str] = None
    ):
        """
        Log performance metrics
        
        Args:
            operation: Name of the operation
            duration_ms: Duration in milliseconds
            context: Context of the operation
            user_id: User ID if available
        """
        perf_data = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "duration_ms": duration_ms,
            "context": context,
            "user_id": user_id
        }
        
        if duration_ms > 5000:  # Slow operation (>5 seconds)
            logger.warning(f"[PERFORMANCE] Slow operation: {perf_data}")
        else:
            logger.info(f"[PERFORMANCE] {perf_data}")
        
        return perf_data


# Global instance
error_monitor = ErrorMonitor()
