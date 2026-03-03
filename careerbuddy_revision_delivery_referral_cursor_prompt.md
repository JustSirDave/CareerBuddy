# CareerBuddy — Revision System, Delivery Confirmation & Referral System
## Cursor Implementation Prompt

---

## Context & Background

CareerBuddy is a Telegram-based AI career document assistant built with FastAPI, PostgreSQL, Redis, and OpenAI GPT-4. Users pay per document (₦7,500 resume/CV, ₦3,000 cover letter, ₦15,000 bundle) and receive DOCX/PDF output via Telegram.

This prompt implements three features:
1. **Guided Revision System** — 1 free revision per paid document, section-by-section
2. **Delivery Confirmation** — 24hr follow-up after document delivery
3. **Referral System** — share a link, earn a free document credit

---

## Architecture Overview

```
backend/app/
├── main.py                   # FastAPI app, startup, scheduler
├── config.py                 # Settings from env
├── models/
│   ├── user.py               # User — add referral fields
│   ├── job.py                # Job — add revision fields
│   └── referral.py           # NEW — Referral model
├── routers/
│   └── webhook.py            # Telegram webhook
├── services/
│   ├── router.py             # handle_inbound() — add revision routing
│   ├── ai.py                 # OpenAI calls
│   ├── renderer.py           # DOCX generation — reused for revision
│   ├── telegram.py           # send_message(), send_document()
│   └── scheduler.py          # NEW — background task scheduler
├── flows/
│   ├── resume.py             # Existing flow
│   └── revision.py           # NEW — Guided revision flow
└── tasks/
    └── delivery_confirmation.py  # NEW — 24hr follow-up task
```

---

---

# FEATURE 1: GUIDED REVISION SYSTEM

---

## What "1 Guided Revision" Means Technically

- Each completed, paid Job gets exactly **1 revision credit** (revision_count = 0, max = 1)
- Revision **reopens specific sections** of the job — not the full flow from scratch
- User is shown a menu of sections to edit, picks one, answers only that section's questions again
- Bot regenerates the full document with the updated section merged in
- revision_count increments to 1 — no further free revisions
- Additional revisions can be sold later (v2)

---

## Revision Flow — Step by Step

### Step 1 — Trigger
User sends `/revise` or taps "Request Revision" button after document delivery.

Bot checks:
- Job status is `done`
- `job.revision_count < 1`
- If revision already used: inform user, offer paid revision (coming soon)

### Step 2 — Section Selection Menu
Bot sends:

```
Which part of your [resume] would you like to update?

1. Basic details (name, contact, location)
2. Work experience
3. Skills
4. Professional summary
5. Education
6. Certifications
7. Projects & links

Reply with the number of the section you want to change.
```

### Step 3 — Guided Section Re-collection
Based on selection, bot asks only that section's questions again, exactly as in the original flow.

Example — User selects "2. Work experience":
```
Let's update your work experience.

Tell me about your most recent role:
Role title, Company name, City, Start date – End date
(e.g. Product Manager, Paystack, Lagos, Jan 2022 – Mar 2024)

Type *done* when you've added all your roles.
```

User re-answers. Bot stores new answers under `job.revision_answers[section]`.

### Step 4 — Preview Confirmation
```
Here's what will change in your [resume]:

Work Experience updated ✓

Ready to regenerate your document?
[Yes, regenerate] [Go back]
```

### Step 5 — Regeneration
Bot merges revision_answers into job.answers, regenerates DOCX + PDF, sends to user.

```
Your updated [resume] is ready! 🎉

This was your 1 free revision.
Need more changes? Paid revisions are coming soon.
```

---

## Files To Create / Modify

### `backend/app/flows/revision.py` — CREATE NEW

```python
"""
Guided revision flow for CareerBuddy.
Handles section selection, re-collection, and document regeneration.
"""

from app.models.job import Job
from app.services.telegram import send_message
from app.services.renderer import generate_docx
from app.services.pdf_renderer import generate_pdf
from sqlalchemy.ext.asyncio import AsyncSession

REVISION_SECTIONS = {
    "1": {"key": "basics", "label": "Basic details"},
    "2": {"key": "experiences", "label": "Work experience"},
    "3": {"key": "skills", "label": "Skills"},
    "4": {"key": "summary", "label": "Professional summary"},
    "5": {"key": "education", "label": "Education"},
    "6": {"key": "certifications", "label": "Certifications"},
    "7": {"key": "projects", "label": "Projects & links"},
}

SECTION_PROMPTS = {
    "basics": (
        "Let's update your basic details.\n\n"
        "Share your updated info:\n"
        "*Full Name, email@example.com, 08012345678, City*"
    ),
    "experiences": (
        "Let's update your work experience.\n\n"
        "Tell me about your most recent role:\n"
        "*Role title, Company, City, Start – End date*\n\n"
        "Type *done* when you've added all roles."
    ),
    "skills": (
        "Let's update your skills.\n\n"
        "Type *suggest* for AI suggestions, or list your skills directly."
    ),
    "summary": (
        "Let's update your professional summary.\n\n"
        "Type *generate* for an AI-written summary, or write your own below."
    ),
    "education": (
        "Let's update your education.\n\n"
        "Format: *Degree, Institution, Year*\n"
        "(e.g. B.Sc Computer Science, University of Lagos, 2019)"
    ),
    "certifications": (
        "List your updated certifications.\n"
        "(e.g. AWS Certified Developer, 2023)\n\nType *skip* if none."
    ),
    "projects": (
        "Share your updated projects and profile links.\n"
        "(e.g. LinkedIn: linkedin.com/in/yourname)\n\nType *skip* if none."
    ),
}

MULTI_STEP_SECTIONS = ["experiences"]

async def start_revision(job: Job, telegram_id: int, db: AsyncSession):
    """Entry point — check eligibility, show section menu."""
    if job.revision_count >= 1:
        await send_message(
            telegram_id,
            "You've used your free revision for this document.\n\n"
            "Paid revisions are coming soon! In the meantime, "
            "you can create a new document with your updates."
        )
        return

    job.revision_answers = {}
    job.answers["_revision_step"] = "select_section"
    await db.commit()

    await send_message(
        telegram_id,
        f"Let's update your {job.type}. Which section would you like to change?\n\n"
        "1. Basic details (name, contact, location)\n"
        "2. Work experience\n"
        "3. Skills\n"
        "4. Professional summary\n"
        "5. Education\n"
        "6. Certifications\n"
        "7. Projects & links\n\n"
        "Reply with the number of the section."
    )

async def handle_revision_step(job: Job, message_text: str, telegram_id: int, db: AsyncSession):
    """Route revision flow based on _revision_step."""
    revision_step = job.answers.get("_revision_step")

    if revision_step == "select_section":
        await _handle_section_selection(job, message_text, telegram_id, db)
    elif revision_step and revision_step.startswith("collecting_"):
        section_key = revision_step.replace("collecting_", "")
        await _handle_section_collection(job, section_key, message_text, telegram_id, db)
    elif revision_step == "confirm":
        await _handle_revision_confirmation(job, message_text, telegram_id, db)

async def _handle_section_selection(job, selection, telegram_id, db):
    section = REVISION_SECTIONS.get(selection.strip())
    if not section:
        await send_message(telegram_id, "Please reply with a number from 1 to 7.")
        return

    job.answers["_revision_section"] = section["key"]
    job.answers["_revision_step"] = f"collecting_{section['key']}"
    await db.commit()
    await send_message(telegram_id, SECTION_PROMPTS[section["key"]])

async def _handle_section_collection(job, section_key, message_text, telegram_id, db):
    if section_key in MULTI_STEP_SECTIONS:
        if message_text.lower().strip() == "done":
            await _show_revision_confirmation(job, section_key, telegram_id, db)
            return
        if section_key not in job.revision_answers:
            job.revision_answers[section_key] = []
        job.revision_answers[section_key].append(message_text)
        await db.commit()
        await send_message(telegram_id, "Got it! Add another role, or type *done* to continue.")
    else:
        job.revision_answers[section_key] = message_text
        await _show_revision_confirmation(job, section_key, telegram_id, db)

async def _show_revision_confirmation(job, section_key, telegram_id, db):
    section_label = next(
        (s["label"] for s in REVISION_SECTIONS.values() if s["key"] == section_key),
        section_key
    )
    job.answers["_revision_step"] = "confirm"
    await db.commit()
    await send_message(
        telegram_id,
        f"Here's what will change in your {job.type}:\n\n"
        f"✓ *{section_label}* updated\n\n"
        "Ready to regenerate your document?\n\n"
        "Type *yes* to regenerate, or *back* to pick a different section."
    )

async def _handle_revision_confirmation(job, message_text, telegram_id, db):
    text = message_text.lower().strip()

    if text == "back":
        job.answers["_revision_step"] = "select_section"
        await db.commit()
        await start_revision(job, telegram_id, db)
        return

    if text not in ("yes", "y", "regenerate"):
        await send_message(telegram_id, "Type *yes* to regenerate, or *back* to pick a different section.")
        return

    await send_message(telegram_id, "Regenerating your document with the updates... ⏳")

    for section_key, value in job.revision_answers.items():
        job.answers[section_key] = value

    job.answers.pop("_revision_step", None)
    job.answers.pop("_revision_section", None)
    job.revision_count += 1
    job.revision_answers = {}
    await db.commit()

    docx_path = await generate_docx(job, telegram_id)
    if docx_path:
        from app.services.telegram import send_document
        await send_document(telegram_id, docx_path, caption=f"Your updated {job.type} is ready! 🎉")

        if job.user.tier == "pro":
            pdf_path = await generate_pdf(job, telegram_id)
            if pdf_path:
                await send_document(telegram_id, pdf_path, caption="PDF version:")

        if job.revision_count >= 1:
            await send_message(
                telegram_id,
                "This was your 1 free revision.\n"
                "Need more changes? Paid revisions are coming soon!"
            )
```

---

### `backend/app/models/job.py` — MODIFY

Add revision fields to Job model:

```python
revision_count = Column(Integer, default=0, nullable=False)
revision_answers = Column(JSON, default=dict, nullable=False)
```

Add to JobStatus enum:

```python
REVISING = "revising"
```

---

### `backend/app/services/router.py` — MODIFY

```python
# Handle /revise command
if message_text == "/revise":
    latest_done_job = await get_latest_done_job(user.id, db)
    if not latest_done_job:
        await send_message(telegram_id, "You don't have any completed documents to revise yet.")
        return
    latest_done_job.status = "revising"
    await db.commit()
    await start_revision(latest_done_job, telegram_id, db)
    return

# Route active revision flow — check BEFORE other routing
if active_job and active_job.status == "revising":
    await handle_revision_step(active_job, message_text, telegram_id, db)
    return
```

---

### Alembic Migration

Create migration for:
- `jobs.revision_count` (Integer, default 0, not null)
- `jobs.revision_answers` (JSON, default {}, not null)

---

---

# FEATURE 2: DELIVERY CONFIRMATION (24HR FOLLOW-UP)

---

## What It Does

24 hours after a document is delivered (Job status transitions to `done`), the bot sends one follow-up message. Sent once per job, never again.

Example message:
```
Hey Ada! 👋

How did your resume land? Hope it's helping with your applications.

Need any tweaks? Send /revise and I'll guide you through it.
Ready for a cover letter? Send /start 🚀
```

---

## Files To Create / Modify

### `backend/app/tasks/delivery_confirmation.py` — CREATE NEW

```python
"""
Delivery confirmation task.
Sends a 24hr follow-up message after document delivery.
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.job import Job, JobStatus
from app.models.user import User
from app.services.telegram import send_message

logger = logging.getLogger(__name__)

CONFIRMATION_MESSAGES = {
    "resume": (
        "Hey {first_name}! 👋\n\n"
        "How did your resume land? Hope it's helping with your applications.\n\n"
        "Need any tweaks? Send /revise and I'll guide you through it.\n"
        "Ready for a cover letter? Send /start 🚀"
    ),
    "cv": (
        "Hey {first_name}! 👋\n\n"
        "Hope your CV is opening doors! How's the job search going?\n\n"
        "Need any tweaks? Send /revise and I'll guide you through it.\n"
        "Want a cover letter to go with it? Send /start 🚀"
    ),
    "cover_letter": (
        "Hey {first_name}! 👋\n\n"
        "Hope that cover letter made a great impression!\n\n"
        "Need any tweaks? Send /revise and I'll guide you through it.\n"
        "Ready to create another document? Send /start 🚀"
    ),
}

async def send_pending_delivery_confirmations(db: AsyncSession):
    """
    Called by scheduler every 30 minutes.
    Finds jobs completed 23–25 hours ago with no follow-up sent yet.
    """
    cutoff_start = datetime.utcnow() - timedelta(hours=25)
    cutoff_end = datetime.utcnow() - timedelta(hours=23)

    result = await db.execute(
        select(Job)
        .where(Job.status == JobStatus.DONE)
        .where(Job.completed_at >= cutoff_start)
        .where(Job.completed_at <= cutoff_end)
        .where(Job.delivery_confirmation_sent == False)
    )
    jobs = result.scalars().all()

    for job in jobs:
        try:
            user = await db.get(User, job.user_id)
            if not user:
                continue

            message_template = CONFIRMATION_MESSAGES.get(job.type, CONFIRMATION_MESSAGES["resume"])
            first_name = user.telegram_first_name or "there"
            await send_message(user.telegram_user_id, message_template.format(first_name=first_name))

            job.delivery_confirmation_sent = True
            await db.commit()
            logger.info(f"Delivery confirmation sent: job_id={job.id}")

        except Exception as e:
            logger.error(f"Delivery confirmation failed for job {job.id}: {e}")
            # Continue — don't let one failure block others
```

---

### `backend/app/services/scheduler.py` — CREATE NEW

```python
"""
Background task scheduler.
Requires: pip install apscheduler
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.db import get_db
from app.tasks.delivery_confirmation import send_pending_delivery_confirmations
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

def start_scheduler():
    scheduler.add_job(
        _run_delivery_confirmations,
        trigger=IntervalTrigger(minutes=30),
        id="delivery_confirmations",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")

async def _run_delivery_confirmations():
    async with get_db() as db:
        await send_pending_delivery_confirmations(db)

def stop_scheduler():
    scheduler.shutdown()
```

---

### `backend/app/main.py` — MODIFY

```python
from app.services.scheduler import start_scheduler, stop_scheduler

@app.on_event("startup")
async def startup():
    # ... existing startup logic ...
    start_scheduler()

@app.on_event("shutdown")
async def shutdown():
    stop_scheduler()
```

---

### `backend/app/models/job.py` — MODIFY (additional fields)

```python
completed_at = Column(DateTime, nullable=True)
delivery_confirmation_sent = Column(Boolean, default=False, nullable=False)
```

In router.py, set `job.completed_at = datetime.utcnow()` every time job transitions to `done`.

---

### `backend/app/models/user.py` — MODIFY

```python
telegram_first_name = Column(String(100), nullable=True)
```

Populate from Telegram payload's `first_name` field when creating/updating user.

---

### Alembic Migration

Create migration for:
- `jobs.completed_at` (DateTime, nullable)
- `jobs.delivery_confirmation_sent` (Boolean, default False)
- `users.telegram_first_name` (String 100, nullable)

---

---

# FEATURE 3: REFERRAL SYSTEM

---

## How It Works

1. User sends `/referral` — bot generates a unique referral link
2. User shares: `https://t.me/YourBotUsername?start=ref_ABC12345`
3. Friend clicks → Telegram auto-sends `/start ref_ABC12345` to the bot
4. When friend completes their **first paid purchase**, referrer earns 1 free document credit
5. Credit applied automatically on referrer's next document — no code needed
6. Both parties notified on conversion

---

## Referral Rules

- Referrer earns 1 free document credit per successful conversion
- Successful = referee's first paid transaction (not just signup)
- No self-referral
- No cap on referrals
- Credits apply to any document type
- Free tier users can use credits — bypasses generation count for that document

---

## Files To Create / Modify

### `backend/app/models/referral.py` — CREATE NEW

```python
"""Referral model."""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base

class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True)
    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    referee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    status = Column(String(20), default="pending")  # pending | converted | rewarded
    converted_at = Column(DateTime, nullable=True)
    rewarded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    referrer = relationship("User", foreign_keys=[referrer_id], backref="referrals_made")
    referee = relationship("User", foreign_keys=[referee_id], backref="referral_used")
```

---

### `backend/app/models/user.py` — MODIFY

```python
referral_credits = Column(Integer, default=0, nullable=False)
referred_by_code = Column(String(20), nullable=True)
```

---

### `backend/app/services/referral.py` — CREATE NEW

```python
"""
Referral service — code generation, signup tracking, conversion, credit issuance.
"""

import secrets
import string
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.referral import Referral
from app.models.user import User
from app.services.telegram import send_message
import logging

logger = logging.getLogger(__name__)

def _generate_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

async def get_or_create_referral_code(user: User, db: AsyncSession) -> str:
    """Return existing referral code or create a new one."""
    result = await db.execute(
        select(Referral)
        .where(Referral.referrer_id == user.id)
        .where(Referral.referee_id == None)
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing.code

    # Ensure uniqueness
    while True:
        code = _generate_code()
        clash = await db.execute(select(Referral).where(Referral.code == code))
        if not clash.scalar_one_or_none():
            break

    referral = Referral(referrer_id=user.id, code=code)
    db.add(referral)
    await db.commit()
    return code

async def handle_referral_signup(new_user: User, ref_code: str, db: AsyncSession):
    """Link new user to referral on first /start with ref code."""
    result = await db.execute(select(Referral).where(Referral.code == ref_code))
    referral = result.scalar_one_or_none()

    if not referral:
        logger.warning(f"Referral code not found: {ref_code}")
        return

    if referral.referrer_id == new_user.id:
        logger.warning(f"Self-referral blocked: user {new_user.id}")
        return

    referral.referee_id = new_user.id
    new_user.referred_by_code = ref_code
    await db.commit()
    logger.info(f"Referral signup linked: code={ref_code} referee={new_user.id}")

async def process_referral_conversion(user: User, db: AsyncSession):
    """
    Call when user completes first paid purchase.
    If they were referred, reward the referrer.
    """
    if not user.referred_by_code:
        return

    result = await db.execute(
        select(Referral)
        .where(Referral.code == user.referred_by_code)
        .where(Referral.status == "pending")
    )
    referral = result.scalar_one_or_none()
    if not referral:
        return

    referral.status = "converted"
    referral.converted_at = datetime.utcnow()
    await db.commit()

    await _issue_credit(referral, db)

async def _issue_credit(referral: Referral, db: AsyncSession):
    """Award credit to referrer and notify both parties."""
    referrer = await db.get(User, referral.referrer_id)
    referee = await db.get(User, referral.referee_id)

    if not referrer:
        return

    referrer.referral_credits += 1
    referral.status = "rewarded"
    referral.rewarded_at = datetime.utcnow()
    await db.commit()

    await send_message(
        referrer.telegram_user_id,
        f"Someone you referred just made their first purchase!\n\n"
        f"You've earned *1 free document credit* 🎉\n\n"
        f"Your credits: *{referrer.referral_credits}*\n\n"
        f"Credits apply automatically on your next document. "
        f"Use /referral to share your link and earn more!"
    )

    if referee:
        await send_message(
            referee.telegram_user_id,
            "A friend referred you to CareerBuddy — they just earned a free credit because of you! 🙌"
        )

async def apply_referral_credit(user: User, db: AsyncSession) -> bool:
    """
    Deduct 1 credit if available. Returns True if credit was applied.
    Call BEFORE initiating payment. If True, skip payment entirely.
    """
    if user.referral_credits > 0:
        user.referral_credits -= 1
        await db.commit()
        logger.info(f"Referral credit applied: user={user.id} remaining={user.referral_credits}")
        return True
    return False
```

---

### `backend/app/services/router.py` — MODIFY

#### /start with referral code:

```python
if message_text.startswith("/start"):
    parts = message_text.split()
    if len(parts) > 1 and parts[1].startswith("ref_"):
        ref_code = parts[1].replace("ref_", "")
        if user_is_new:
            await handle_referral_signup(user, ref_code, db)
```

#### /referral command:

```python
if message_text == "/referral":
    code = await get_or_create_referral_code(user, db)
    bot_username = settings.TELEGRAM_BOT_USERNAME
    link = f"https://t.me/{bot_username}?start=ref_{code}"

    await send_message(
        telegram_id,
        f"Share your link and earn a *free document credit* every time "
        f"someone you refer makes their first purchase!\n\n"
        f"Your link:\n{link}\n\n"
        f"*Your credits:* {user.referral_credits}\n\n"
        f"Credits apply automatically on your next document — no code needed."
    )
    return
```

#### Apply credit before payment:

```python
# In payment initiation flow, before creating Paystack charge:
credit_applied = await apply_referral_credit(user, db)
if credit_applied:
    await send_message(telegram_id, "A referral credit has been applied — this document is on us! 🎉")
    await finalize_document_without_payment(job, telegram_id, db)
    return
# Otherwise proceed to Paystack as normal
```

#### Trigger conversion on first payment:

```python
# In Paystack webhook handler, after confirming successful payment:
user_payment_count = await get_completed_payment_count(user.id, db)
if user_payment_count == 1:
    await process_referral_conversion(user, db)
```

---

### `backend/app/config.py` — MODIFY

```python
TELEGRAM_BOT_USERNAME: str = "YourBotUsername"  # Without @ sign
```

---

### Alembic Migration

Create migration for:
- New `referrals` table (full schema above)
- `users.referral_credits` (Integer, default 0, not null)
- `users.referred_by_code` (String 20, nullable)

---

---

# TESTS TO WRITE

### `backend/tests/test_revision.py` — CREATE NEW

```python
# 1. /revise on completed job → section menu shown, job.status = revising
# 2. /revise on job with revision_count=1 → "no more free revisions" message
# 3. /revise with no completed jobs → appropriate message
# 4. Section "2" selected → experience prompt sent, _revision_step = collecting_experiences
# 5. Invalid section "9" → re-prompt for valid number
# 6. Experience section → accumulates entries until "done"
# 7. Single-answer section (education) → one answer, moves to confirm
# 8. "back" at confirm → returns to section menu
# 9. "yes" at confirm → document regenerated, revision_count = 1
# 10. revision_answers merged into job.answers before regeneration
# 11. Render failure during revision → error handled, job data preserved
# 12. Revision routing checked before normal flow routing in handle_inbound
```

### `backend/tests/test_delivery_confirmation.py` — CREATE NEW

```python
# 1. Job completed 24hrs ago → confirmation sent, delivery_confirmation_sent = True
# 2. Confirmation already sent → not sent again
# 3. Job completed 12hrs ago → not sent (too early)
# 4. Job completed 48hrs ago → not sent (outside window)
# 5. Bot blocked (403) → error caught, other jobs still processed
# 6. completed_at set when job → done in router
# 7. Message varies by job type (resume vs cv vs cover_letter)
# 8. telegram_first_name used in message; "there" used as fallback
```

### `backend/tests/test_referral.py` — CREATE NEW

```python
# 1. /referral → unique link generated and shown
# 2. /referral again → same link returned, not a new one
# 3. /start ref_CODE new user → referred_by_code stored
# 4. Self-referral → rejected silently, signup continues
# 5. Invalid ref code → handled gracefully, signup continues normally
# 6. Referee first purchase → referrer gets +1 credit, both notified
# 7. Referee second purchase → no additional credit
# 8. apply_referral_credit with credits > 0 → True, credit decremented
# 9. apply_referral_credit with credits = 0 → False, no change
# 10. /referral shows correct credit balance
# 11. Credit applied → Paystack charge skipped, document finalized
# 12. Referral status progresses: pending → converted → rewarded
```

---

## Summary of All Files

| File | Action | Feature |
|---|---|---|
| `backend/app/flows/revision.py` | Create new | Revision |
| `backend/app/models/referral.py` | Create new | Referral |
| `backend/app/services/referral.py` | Create new | Referral |
| `backend/app/services/scheduler.py` | Create new | Delivery confirmation |
| `backend/app/tasks/delivery_confirmation.py` | Create new | Delivery confirmation |
| `backend/app/models/job.py` | Modify | Revision + Delivery |
| `backend/app/models/user.py` | Modify | Delivery + Referral |
| `backend/app/services/router.py` | Modify | All three |
| `backend/app/services/payments.py` | Modify | Referral credit apply |
| `backend/app/routers/webhook.py` | Modify | Referral conversion trigger |
| `backend/app/config.py` | Modify | Referral bot username |
| `backend/app/main.py` | Modify | Scheduler startup/shutdown |
| `backend/migrations/versions/xxx_revision_delivery_referral.py` | Create new | All three |
| `backend/tests/test_revision.py` | Create new | Revision |
| `backend/tests/test_delivery_confirmation.py` | Create new | Delivery |
| `backend/tests/test_referral.py` | Create new | Referral |

---

## Definition of Done

**Revision:**
- [ ] /revise works on completed jobs, blocked on jobs with revision_count >= 1
- [ ] Section menu shows all 7 sections with correct prompts
- [ ] Multi-step sections (experiences) loop until "done"
- [ ] Single-answer sections collect one answer and move to confirm
- [ ] "back" at confirm returns to section menu
- [ ] "yes" merges revision_answers, regenerates document, increments revision_count
- [ ] Render failure during revision preserves all data
- [ ] Revision routing checked before normal flow routing

**Delivery Confirmation:**
- [ ] completed_at stamped on every job → done transition
- [ ] Scheduler runs every 30 minutes via APScheduler
- [ ] Follow-up sent exactly once in the 23–25hr window
- [ ] delivery_confirmation_sent flag prevents duplicates
- [ ] Message personalised by first_name and document type
- [ ] Bot-blocked users handled without crashing the scheduler run

**Referral:**
- [ ] /referral generates a unique, persistent link per user
- [ ] /start ref_CODE links new user to referrer on first signup only
- [ ] Self-referral silently rejected
- [ ] Credit issued only on referee's first paid purchase
- [ ] Credit applied automatically before next charge, Paystack skipped
- [ ] Both parties notified on conversion
- [ ] Credit balance shown accurately in /referral message
- [ ] All edge cases handled: invalid code, repeat conversion, no referral
