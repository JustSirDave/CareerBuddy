# CareerBuddy — Error Recovery & Conversation Feel
## Cursor Implementation Prompt

---

## Context & Background

CareerBuddy is a Telegram-based AI career document assistant built with FastAPI, PostgreSQL, Redis, and OpenAI GPT-4. Users interact via chat to create resumes, CVs, and cover letters through a step-based conversation flow.

**The problem:** When things go wrong — invalid input, dropped sessions, unexpected messages, API failures, mid-flow confusion — the bot either crashes silently, sends a generic error, or does nothing. This kills trust and abandons users at the worst possible moment.

**The goal:** Implement a comprehensive error recovery system that:
1. Catches every failure point gracefully
2. Responds with human, warm, context-aware messages (never generic "An error occurred")
3. Guides the user back on track without losing their progress
4. Logs errors properly for debugging
5. Handles re-entry after dropout (user comes back hours/days later)

---

## Architecture Overview

```
backend/app/
├── main.py                   # FastAPI app, global exception handlers
├── config.py                 # Settings from env
├── models/
│   ├── user.py               # User model
│   └── job.py                # Job model — status, answers, _step
├── routers/
│   └── webhook.py            # Telegram webhook — first point of failure
├── services/
│   ├── router.py             # handle_inbound() — main conversation router
│   ├── ai.py                 # OpenAI calls — can fail/timeout
│   ├── telegram.py           # send_message() — can fail
│   ├── renderer.py           # DOCX generation — can fail
│   ├── pdf_renderer.py       # PDF generation — can fail
│   ├── payments.py           # Quota/payment checks
│   └── idempotency.py        # Redis dedup — can fail
└── flows/
    └── resume.py             # Step validators — where bad input hits first
```

**Key facts:**
- All user input passes through `handle_inbound()` in `services/router.py`
- Step validation happens inside flow handlers (e.g. `flows/resume.py`)
- Job progress lives in `Job.answers` JSON — preserving this is critical during recovery
- `Job.status` drives the state machine: `collecting → draft_ready → preview_ready → done`
- Redis is used for idempotency — if Redis is down, dedup fails silently

---

## Error Categories To Handle

### Category 1 — Invalid User Input
User provides input that fails validation for the current step.

**Examples:**
- Email step: user types "john" instead of "john@email.com"
- Phone step: user types "call me" instead of a number
- Date step: user types "last year" instead of "2022–2024"
- Experience bullets: user sends only 1 bullet when 2 minimum are required
- Skills selection: user types "xyz" when expected format is numbers

**Current behaviour:** Either silent ignore, confusing re-prompt, or crash.

**Expected behaviour:** Friendly, specific correction message that explains exactly what's wrong and shows the expected format.

---

### Category 2 — User Dropout & Re-entry
User starts a flow, disappears for hours or days, then comes back.

**Examples:**
- User at step 3 of 11 sends `/start` again
- User at step 7 sends a completely off-topic message
- User at step 5 sends `/help`

**Current behaviour:** Either resets their job or confuses the router.

**Expected behaviour:** Detect active job, remind user where they left off, offer to continue or restart.

---

### Category 3 — AI Service Failures
OpenAI API call fails, times out, or returns malformed response.

**Failure points:**
- Skills suggestion generation
- Professional summary generation
- Onboarding intent detection

**Current behaviour:** Unhandled exception, silent failure, or crash.

**Expected behaviour:** Graceful fallback — either retry once silently, or continue the flow without AI enhancement with a gentle explanation.

---

### Category 4 — Document Generation Failures
DOCX or PDF renderer fails mid-generation.

**Failure points:**
- `renderer.py` throws during DOCX build
- `pdf_renderer.py` or LibreOffice conversion fails
- File write to `output/jobs/{job_id}/` fails (disk full, permissions)

**Current behaviour:** Job gets stuck, user receives nothing.

**Expected behaviour:** Inform user clearly, preserve their data, offer to retry.

---

### Category 5 — Telegram Send Failures
Bot fails to send a message or document to the user.

**Failure points:**
- User has blocked the bot
- Telegram API rate limit hit
- Network timeout sending large document file

**Current behaviour:** Unhandled exception, no retry.

**Expected behaviour:** Retry with exponential backoff for transient failures; log and skip for permanent failures (e.g. bot blocked).

---

### Category 6 — Database / Redis Failures
Postgres or Redis is temporarily unavailable.

**Current behaviour:** 500 error, Telegram gets no response, retries.

**Expected behaviour:** Return 200 to Telegram immediately (to stop retries), log the failure, attempt recovery on next message.

---

### Category 7 — Webhook-Level Errors
Malformed payload, missing fields, unexpected update types.

**Current behaviour:** Unhandled exception propagates to FastAPI.

**Expected behaviour:** Catch at webhook level, return 200 to Telegram, log for debugging.

---

## What To Build

### 1. Central Error Handler — `services/error_handler.py` ← CREATE NEW

```python
"""
CareerBuddy Error Handler
Centralised error recovery, messaging, and logging.
"""

import logging
from enum import Enum
from app.services.telegram import send_message

logger = logging.getLogger(__name__)

class ErrorType(Enum):
    INVALID_INPUT = "invalid_input"
    AI_FAILURE = "ai_failure"
    RENDER_FAILURE = "render_failure"
    SEND_FAILURE = "send_failure"
    DB_FAILURE = "db_failure"
    UNEXPECTED = "unexpected"

# All error messages live here — never inline in business logic
ERROR_MESSAGES = {
    # Input validation errors — step-specific
    "invalid_email": "That doesn't look like a valid email address. Could you double-check it? (e.g. yourname@gmail.com)",
    "invalid_phone": "I need a valid phone number here. Try something like 08012345678 or +2348012345678.",
    "invalid_date_range": "I need dates in this format: *Month Year – Month Year* (e.g. Jan 2022 – Mar 2024). Give it another try.",
    "too_few_bullets": "Add at least 2 achievement bullets for this role. What did you accomplish there?",
    "invalid_skills_selection": "Just type the numbers of the skills you want, separated by commas (e.g. 1, 3, 5). Or type your own skills.",
    "basics_format": "Please share your details like this:\n*Full Name, email@example.com, 08012345678, Lagos*",
    
    # AI failures
    "ai_skills_failed": "I couldn't generate skill suggestions right now — no worries, just type your skills directly and I'll include them.",
    "ai_summary_failed": "I had trouble generating your summary. You can write one yourself, or type *skip* and I'll use a standard format.",
    "ai_generic_failed": "My AI brain had a hiccup there 😅 Let's keep going — I'll do my best without it.",
    
    # Render failures
    "docx_render_failed": "I hit a snag generating your document. Your information is safe — type *retry* to try again.",
    "pdf_render_failed": "I couldn't convert to PDF right now. Your DOCX is ready though — type */pdf* again in a moment to retry.",
    
    # Session/dropout
    "job_in_progress": "Hey, you're in the middle of creating your {doc_type}! Want to continue where you left off, or start fresh?\n\n[Continue] [Start Fresh]",
    "step_reminder": "We're on: *{step_label}*\n\n{step_prompt}",
    "session_expired_graceful": "It's been a while! Your {doc_type} is still saved. Want to pick up where you left off?",
    
    # Generic fallback — use only as last resort
    "generic_fallback": "Something unexpected happened on my end. Your progress is saved — just send any message and I'll get us back on track.",
}

async def handle_error(
    error_type: ErrorType,
    telegram_id: int,
    error_key: str,
    context: dict = None,
    exception: Exception = None,
):
    """
    Central error handler. Logs the error, sends appropriate recovery message.
    context: dict of template variables for message formatting (e.g. doc_type, step_label)
    """
    # Log with full context
    logger.error(
        f"[{error_type.value}] key={error_key} telegram_id={telegram_id} "
        f"context={context} exception={exception}",
        exc_info=exception is not None,
    )
    
    # Get message, format with context if provided
    message = ERROR_MESSAGES.get(error_key, ERROR_MESSAGES["generic_fallback"])
    if context:
        message = message.format(**context)
    
    # Send to user — wrap in try/except so error handler itself never crashes
    try:
        await send_message(telegram_id, message)
    except Exception as send_exc:
        logger.critical(f"Failed to send error message to {telegram_id}: {send_exc}")
```

---

### 2. Input Validators — `flows/validators.py` ← CREATE NEW

Centralise all step-level input validation. Each validator returns `(is_valid: bool, error_key: str | None)`.

```python
"""
Step-level input validators for CareerBuddy flows.
Each returns (is_valid, error_key_or_None).
"""

import re
from typing import Tuple, Optional

def validate_email(value: str) -> Tuple[bool, Optional[str]]:
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w{2,}$'
    return (bool(re.match(pattern, value.strip())), None) if re.match(pattern, value.strip()) else (False, "invalid_email")

def validate_phone(value: str) -> Tuple[bool, Optional[str]]:
    # Accepts Nigerian formats and international E.164
    cleaned = re.sub(r'[\s\-\(\)]', '', value)
    pattern = r'^(\+?234|0)[789]\d{9}$'
    return (True, None) if re.match(pattern, cleaned) else (False, "invalid_phone")

def validate_date_range(value: str) -> Tuple[bool, Optional[str]]:
    # Accepts "Jan 2022 – Mar 2024" or "2022 – Present"
    pattern = r'.{3,}\s*[–\-]\s*.{3,}'
    return (True, None) if re.match(pattern, value.strip()) else (False, "invalid_date_range")

def validate_basics(value: str) -> Tuple[bool, Optional[str]]:
    # Expects: Name, email, phone, location (comma-separated, 4 parts)
    parts = [p.strip() for p in value.split(',')]
    if len(parts) < 4:
        return (False, "basics_format")
    _, email_valid, _ = validate_email(parts[1])
    if not email_valid:
        return (False, "invalid_email")
    return (True, None)

def validate_experience_bullets(bullets: list) -> Tuple[bool, Optional[str]]:
    if len(bullets) < 2:
        return (False, "too_few_bullets")
    return (True, None)

def validate_skills_selection(value: str, max_options: int) -> Tuple[bool, Optional[str]]:
    # Accept comma-separated numbers or free text
    if any(c.isdigit() for c in value):
        numbers = re.findall(r'\d+', value)
        if all(1 <= int(n) <= max_options for n in numbers):
            return (True, None)
        return (False, "invalid_skills_selection")
    # Free text skills — always valid
    return (True, None)
```

---

### 3. AI Failure Handling — `services/ai.py` ← MODIFY

Wrap all OpenAI calls with retry + graceful fallback:

```python
import asyncio
from app.services.error_handler import handle_error, ErrorType

MAX_AI_RETRIES = 2
AI_RETRY_DELAY = 1.5  # seconds

async def call_openai_with_retry(prompt: str, telegram_id: int, error_key: str, fallback=None):
    """
    Call OpenAI with automatic retry. Returns result or fallback on failure.
    Never raises — always returns something usable.
    """
    last_exception = None
    for attempt in range(MAX_AI_RETRIES):
        try:
            # ... existing OpenAI call logic ...
            pass
        except Exception as e:
            last_exception = e
            if attempt < MAX_AI_RETRIES - 1:
                await asyncio.sleep(AI_RETRY_DELAY * (attempt + 1))
    
    # All retries exhausted
    await handle_error(
        ErrorType.AI_FAILURE,
        telegram_id,
        error_key,
        exception=last_exception,
    )
    return fallback  # Caller decides what to do with None/fallback

# Apply to all existing AI functions:
async def suggest_skills(job_data: dict, telegram_id: int) -> list:
    result = await call_openai_with_retry(
        prompt=build_skills_prompt(job_data),
        telegram_id=telegram_id,
        error_key="ai_skills_failed",
        fallback=[],  # Empty list — flow continues, user types manually
    )
    return result or []

async def generate_summary(job_data: dict, telegram_id: int) -> str:
    result = await call_openai_with_retry(
        prompt=build_summary_prompt(job_data),
        telegram_id=telegram_id,
        error_key="ai_summary_failed",
        fallback=None,  # None signals flow to ask user to write their own
    )
    return result
```

---

### 4. Renderer Failure Handling — `services/renderer.py` & `pdf_renderer.py` ← MODIFY

```python
from app.services.error_handler import handle_error, ErrorType

async def generate_docx(job: Job, telegram_id: int) -> str | None:
    """Returns file path on success, None on failure."""
    try:
        # ... existing DOCX generation logic ...
        return file_path
    except Exception as e:
        await handle_error(
            ErrorType.RENDER_FAILURE,
            telegram_id,
            "docx_render_failed",
            context={"doc_type": job.type},
            exception=e,
        )
        # Set job status to indicate render failed but data is safe
        job.status = "render_failed"
        return None

async def generate_pdf(job: Job, telegram_id: int) -> str | None:
    """Returns file path on success, None on failure."""
    try:
        # ... existing PDF generation logic ...
        return file_path
    except Exception as e:
        await handle_error(
            ErrorType.RENDER_FAILURE,
            telegram_id,
            "pdf_render_failed",
            exception=e,
        )
        return None
```

Add `render_failed` to valid Job statuses in `models/job.py`.

---

### 5. Dropout & Re-entry Handling — `services/router.py` ← MODIFY

#### 5a. Detect returning user mid-flow

In `handle_inbound()`, before processing any message, check for active jobs:

```python
async def handle_inbound(telegram_id: int, first_name: str, message_text: str, db: AsyncSession):
    user = await get_or_create_user(telegram_id, db)
    active_job = await get_active_job(user.id, db)
    
    # --- DROPOUT RECOVERY ---
    if active_job and message_text not in GLOBAL_COMMANDS:
        time_since_last = datetime.utcnow() - active_job.updated_at
        
        if time_since_last > timedelta(hours=6):
            # User has been away a while — remind them gently
            await send_session_reminder(telegram_id, active_job)
            return
        
        # User is mid-flow but sent something unexpected
        current_step = active_job.answers.get("_step")
        if not is_valid_for_step(message_text, current_step):
            await send_step_reminder(telegram_id, active_job, current_step)
            return
    
    # --- Continue with normal routing ---
```

#### 5b. Step reminder message

```python
STEP_LABELS = {
    "basics": "Your basic details",
    "target_role": "Target job role",
    "experiences": "Work experience",
    "experience_bullets": "Achievement bullets",
    "skills": "Skills",
    "summary": "Professional summary",
    "education": "Education",
    "certifications": "Certifications",
    "profiles": "Online profiles",
    "projects": "Projects",
    "preview": "Final preview",
}

STEP_REPROMPTS = {
    "basics": "What's your full name, email, phone, and location?\n(e.g. Ada Obi, ada@email.com, 08012345678, Lagos)",
    "target_role": "What job title are you applying for?",
    "experiences": "Tell me about your work experience — role, company, city, and dates.",
    # ... etc for all steps
}

async def send_step_reminder(telegram_id: int, job: Job, step: str):
    step_label = STEP_LABELS.get(step, step)
    step_prompt = STEP_REPROMPTS.get(step, "Let's continue from where we left off.")
    
    await send_message(
        telegram_id,
        f"We're still working on your {job.type} 📄\n\n"
        f"Current step: *{step_label}*\n\n{step_prompt}"
    )

async def send_session_reminder(telegram_id: int, job: Job):
    await send_message(
        telegram_id,
        f"Welcome back! 👋 Your {job.type} is still here, right where you left it.\n\n"
        f"Want to continue, or start something new?\n\n"
        f"[Continue] [Start Fresh]"
    )
```

---

### 6. Telegram Send Failure — `services/telegram.py` ← MODIFY

Add retry with exponential backoff for all outbound sends:

```python
import asyncio
import httpx

MAX_SEND_RETRIES = 3
RETRY_BASE_DELAY = 1  # seconds

async def send_message(telegram_id: int, text: str, **kwargs) -> bool:
    """Send message with retry. Returns True on success, False on permanent failure."""
    last_error = None
    for attempt in range(MAX_SEND_RETRIES):
        try:
            response = await _do_send_message(telegram_id, text, **kwargs)
            if response.status_code == 200:
                return True
            
            # 403 = bot blocked by user — don't retry
            if response.status_code == 403:
                logger.warning(f"Bot blocked by user {telegram_id}")
                return False
                
            # 429 = rate limit — respect Retry-After header
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 5))
                await asyncio.sleep(retry_after)
                continue
                
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = e
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            await asyncio.sleep(delay)
    
    logger.error(f"Failed to send message to {telegram_id} after {MAX_SEND_RETRIES} attempts: {last_error}")
    return False

async def send_document(telegram_id: int, file_path: str, **kwargs) -> bool:
    """Send document with retry. Large files get more generous timeout."""
    # Same pattern as send_message but with longer timeout for file uploads
    pass
```

---

### 7. Webhook-Level Error Handling — `routers/webhook.py` ← MODIFY

Wrap the entire webhook handler so Telegram always gets a 200:

```python
from fastapi import Request, Response
import logging

logger = logging.getLogger(__name__)

@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Malformed webhook payload: {e}")
        return Response(status_code=200)  # Always 200 to stop Telegram retries
    
    try:
        await process_telegram_update(body, db)
    except Exception as e:
        # Log but never let this propagate — Telegram will retry if we 500
        logger.exception(f"Unhandled error processing update: {body.get('update_id')} — {e}")
    
    return Response(status_code=200)
```

---

### 8. Job Status Addition — `models/job.py` ← MODIFY

Add `render_failed` as a valid status:

```python
class JobStatus(str, Enum):
    COLLECTING = "collecting"
    DRAFT_READY = "draft_ready"
    PREVIEW_READY = "preview_ready"
    PAYMENT_REQUIRED = "payment_required"
    RENDER_FAILED = "render_failed"   # ← ADD THIS
    DONE = "done"
```

Handle `render_failed` in `handle_inbound()` — if user sends any message and their job is in `render_failed` status, auto-retry generation before responding.

---

### 9. Structured Logging — `main.py` ← MODIFY

Configure structured logging at app startup so errors are traceable:

```python
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "time": self.formatTime(record),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
```

---

### 10. Tests To Write

Create `backend/tests/test_error_recovery.py`:

```python
# Input validation tests
# 1. Invalid email in basics step → correct error message sent
# 2. Invalid phone → correct error message sent
# 3. Too few experience bullets → correct error message sent
# 4. Invalid skills selection → correct error message sent
# 5. Valid input after failed input → flow continues correctly

# AI failure tests
# 6. OpenAI skills call fails → fallback message sent, flow continues to manual input
# 7. OpenAI summary call fails → fallback message sent, user prompted to write own
# 8. OpenAI retries on transient failure → succeeds on second attempt, no error message

# Render failure tests
# 9. DOCX render fails → error message sent, job status = render_failed, answers preserved
# 10. PDF render fails → DOCX still sent, error message explains PDF failed
# 11. User retries after render_failed → generation retried automatically

# Dropout recovery tests
# 12. User at step 5 sends /start → session reminder shown, continue/restart offered
# 13. User absent 6+ hours returns → welcome back message shown
# 14. User mid-flow sends off-topic message → step reminder shown
# 15. User mid-flow sends /help → help shown, then step reminder appended

# Webhook tests
# 16. Malformed JSON payload → 200 returned, error logged, no crash
# 17. Missing update_id → 200 returned, error logged
# 18. DB down during webhook → 200 returned, error logged

# Telegram send failure tests
# 19. Bot blocked (403) → no retry, logged, returns False
# 20. Rate limited (429) → respects Retry-After, retries once
# 21. Network timeout → retries with backoff up to MAX_SEND_RETRIES
```

---

## Summary of Files Changed

| File | Action | Purpose |
|---|---|---|
| `backend/app/services/error_handler.py` | **Create new** | Central error handling & messaging |
| `backend/app/flows/validators.py` | **Create new** | Input validation per step |
| `backend/app/services/ai.py` | Modify | Add retry + graceful fallback |
| `backend/app/services/router.py` | Modify | Dropout detection, re-entry handling |
| `backend/app/services/telegram.py` | Modify | Retry + backoff for sends |
| `backend/app/services/renderer.py` | Modify | Catch + recover from render errors |
| `backend/app/services/pdf_renderer.py` | Modify | Catch + recover from PDF errors |
| `backend/app/routers/webhook.py` | Modify | Always return 200, catch all exceptions |
| `backend/app/models/job.py` | Modify | Add `render_failed` status |
| `backend/app/main.py` | Modify | Structured JSON logging |
| `backend/tests/test_error_recovery.py` | **Create new** | Full test coverage |

---

## Definition of Done

- [ ] All user-facing errors produce warm, specific, helpful messages — zero generic "An error occurred"
- [ ] Invalid input at any step shows the correct format and re-prompts
- [ ] AI failures are retried silently; flow continues with fallback if all retries fail
- [ ] DOCX render failure preserves job data and prompts retry
- [ ] PDF render failure still delivers DOCX and explains the issue
- [ ] Users returning mid-flow get a session reminder with current step context
- [ ] Users absent 6+ hours get a "welcome back" message before resuming
- [ ] Telegram webhook always returns 200 — never crashes or causes Telegram to retry indefinitely
- [ ] Bot-blocked (403) errors are logged and skipped — no infinite retry
- [ ] Rate limit (429) errors are handled with Retry-After respect
- [ ] All errors are logged in structured JSON format with full context
- [ ] `render_failed` job status exists and triggers auto-retry on next user message
- [ ] All tests written and passing
- [ ] No regression in existing resume/CV/cover letter/onboarding flows
