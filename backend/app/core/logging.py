"""
Logging configuration - Centralized logging setup
TODO: Implement structured logging with:
- Log rotation
- Different log levels per environment
- Structured output (JSON for production)
- Integration with logging services (e.g., Sentry, CloudWatch)
"""
from loguru import logger
from app.config import settings

# Current logging is handled by loguru defaults
# Future: Add custom configuration here
