"""
Step-level input validators for CareerBuddy flows.
Each returns (is_valid, error_key_or_None).
Author: Sir Dave
"""
import re
from typing import Tuple, Optional


def validate_email(value: str) -> Tuple[bool, Optional[str]]:
    if not value or not value.strip():
        return (False, "invalid_email")
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w{2,}$"
    if re.match(pattern, value.strip()):
        return (True, None)
    return (False, "invalid_email")


def validate_phone(value: str) -> Tuple[bool, Optional[str]]:
    if not value or not value.strip():
        return (False, "invalid_phone")
    cleaned = re.sub(r"[\s\-\(\)]", "", value.strip())
    pattern = r"^(\+?234|0)?[789]\d{9}$"
    if re.match(pattern, cleaned) and len(cleaned) >= 10:
        return (True, None)
    return (False, "invalid_phone")


def validate_date_range(value: str) -> Tuple[bool, Optional[str]]:
    if not value or not value.strip():
        return (False, "invalid_date_range")
    pattern = r".{3,}\s*[–\-]\s*.{3,}"
    if re.match(pattern, value.strip()):
        return (True, None)
    return (False, "invalid_date_range")


def validate_basics(value: str) -> Tuple[bool, Optional[str]]:
    parts = [p.strip() for p in (value or "").split(",")]
    if len(parts) < 4:
        return (False, "basics_format")
    is_valid, _ = validate_email(parts[1])
    if not is_valid:
        return (False, "invalid_email")
    is_valid, _ = validate_phone(parts[2])
    if not is_valid:
        return (False, "invalid_phone")
    return (True, None)


def validate_experience_bullets(bullets: list) -> Tuple[bool, Optional[str]]:
    if not bullets or len(bullets) < 2:
        return (False, "too_few_bullets")
    return (True, None)


def validate_skills_selection(value: str, max_options: int) -> Tuple[bool, Optional[str]]:
    if not value or not value.strip():
        return (False, "invalid_skills_selection")
    if any(c.isdigit() for c in value):
        numbers = re.findall(r"\d+", value)
        if numbers and all(1 <= int(n) <= max_options for n in numbers):
            return (True, None)
        return (False, "invalid_skills_selection")
    return (True, None)
