# CareerBuddy — Onboarding Flow Improvement
## Cursor Implementation Prompt

---

## Context & Background

CareerBuddy is a Telegram-based AI career document assistant built with FastAPI, PostgreSQL, Redis, and OpenAI GPT-4. Users interact via chat to create resumes, CVs, and cover letters.

**The problem:** The current onboarding (`/start`) immediately drops a document-type menu on the user. It's cold, transactional, and feels like a vending machine rather than a career assistant.

**The goal:** Replace the cold menu drop with a warm, conversational onboarding flow that:
1. Greets the user personally
2. Asks a single "tell me about yourself" opener
3. Infers intent from their response using AI
4. Transitions naturally into the appropriate document flow
5. Handles returning users differently from new users

---

## Architecture Overview

```
backend/app/
├── main.py                  # FastAPI app
├── config.py                # Settings from env
├── models/
│   └── user.py              # User model (tier, generation_count, etc.)
├── routers/
│   └── webhook.py           # Telegram webhook entry point
├── services/
│   ├── router.py            # handle_inbound() — main conversation router
│   ├── ai.py                # OpenAI calls
│   ├── telegram.py          # send_message(), send_menu(), send_document()
│   └── payments.py          # quota checks
└── flows/
    └── resume.py            # Step-based flow logic
```

**Key facts:**
- Entry point for all Telegram messages: `services/router.py` → `handle_inbound()`
- `/start` command is currently handled inside `handle_inbound()` as a global command
- User state is tracked via `Job.status` and `Job.answers._step`
- New users have no prior `Job` records
- Returning users may have completed jobs or an active job in progress

---

## What To Build

### 1. New User Onboarding Flow

When a **new user** sends `/start` (no prior jobs, first time):

**Step 1 — Warm Welcome**
Send a warm, human greeting. Do NOT show a menu yet.

```
Hey [first_name] 👋 Welcome to CareerBuddy!

I'm your personal career document assistant. I help you create 
professional, ATS-optimized resumes, CVs, and cover letters — 
through a simple conversation, in minutes.

Before we dive in — what brings you here today? 
Tell me a little about what you're looking for. 
(e.g. "I need a new resume", "I'm applying for a job at GTBank", 
"I want to update my CV")
```

**Step 2 — AI Intent Detection**
Take the user's free-text response and call OpenAI to classify intent:

```python
# Possible intents:
# - "resume" → start resume flow
# - "cv" → start CV flow  
# - "cover_letter" → start cover letter flow
# - "bundle" → explain bundle, ask which to start with
# - "unclear" → ask a clarifying follow-up
```

Prompt for intent detection:
```
You are an assistant helping classify a job seeker's intent.
Based on their message, return ONLY a JSON object:
{
  "intent": "resume" | "cv" | "cover_letter" | "bundle" | "unclear",
  "confidence": "high" | "low",
  "extracted_role": "<job title if mentioned, else null>",
  "extracted_company": "<company name if mentioned, else null>"
}
Message: "{user_message}"
```

**Step 3 — Transition**
- High confidence intent → acknowledge and transition directly into the flow, pre-filling any extracted data (role, company) into `Job.answers`
- Low confidence / unclear → show the menu with a softer prompt:

```
Got it! Let me show you what I can help you with:
[Resume] [CV] [Cover Letter] [Bundle]
```

---

### 2. Returning User Onboarding

When a **returning user** sends `/start`:

**Case A — Has completed jobs, no active job:**
```
Welcome back, [first_name]! 👋

Good to see you again. Ready to create another document?
What do you need today?
[Resume] [CV] [Cover Letter] [Bundle]
```

**Case B — Has an active job in progress:**
```
Hey [first_name], you've got a [resume] in progress! 

Want to continue where you left off, or start something new?
[Continue] [Start Fresh]
```

---

### 3. Onboarding State Tracking

Add an `onboarding_step` field to track where a new user is in the onboarding:

**Option A (preferred) — Store in User model:**
Add a column to the `users` table:
```python
onboarding_complete = Column(Boolean, default=False)
onboarding_step = Column(String, nullable=True)  # "awaiting_intent_response"
```

**Option B — Store in a temporary Job:**
Create a special Job with `type="onboarding"` and `status="collecting"` to track the onboarding conversation using the existing state machine.

Use **Option A** — it's cleaner and doesn't pollute the jobs table.

Create an Alembic migration for these new columns.

---

### 4. Files To Create / Modify

#### `backend/app/flows/onboarding.py` ← CREATE NEW

```python
"""
Onboarding flow for new CareerBuddy users.
Handles the warm welcome → intent detection → flow transition sequence.
"""

from app.services.ai import detect_onboarding_intent
from app.services.telegram import send_message, send_menu
from app.models.user import User
from app.models.job import Job
from sqlalchemy.ext.asyncio import AsyncSession

ONBOARDING_WELCOME = """
Hey {first_name} 👋 Welcome to CareerBuddy!

I'm your personal career document assistant. I help you create professional, ATS-optimized resumes, CVs, and cover letters — through a simple conversation, in minutes.

Before we dive in — what brings you here today? Tell me a little about what you're looking for.

_(e.g. "I need a new resume", "I'm applying for a job at GTBank", "I want to update my CV")_
"""

async def handle_new_user_welcome(user: User, telegram_id: int, first_name: str, db: AsyncSession):
    """Send warm welcome to brand new user, set onboarding_step."""
    # Implementation here
    pass

async def handle_onboarding_intent_response(user: User, message_text: str, telegram_id: int, db: AsyncSession):
    """
    Process user's free-text response to the welcome message.
    Detect intent, transition to appropriate flow or show menu.
    """
    # Call AI intent detection
    # On high confidence: transition to flow, pre-fill extracted data
    # On low confidence: show soft menu
    pass
```

#### `backend/app/services/ai.py` ← MODIFY

Add a new function:

```python
async def detect_onboarding_intent(user_message: str) -> dict:
    """
    Classify user's onboarding message into document intent.
    Returns: {intent, confidence, extracted_role, extracted_company}
    """
    # OpenAI call with the intent detection prompt
    # Parse and return JSON response
    pass
```

#### `backend/app/services/router.py` ← MODIFY

Modify `handle_inbound()` to:

1. On `/start` command:
   - Check if `user.onboarding_complete is False` AND no prior jobs → call `handle_new_user_welcome()`
   - Check if returning user with active job → show continue prompt
   - Otherwise → show returning user menu

2. When `user.onboarding_step == "awaiting_intent_response"`:
   - Route the user's message to `handle_onboarding_intent_response()` BEFORE checking for active jobs or commands
   - This must be checked early in the routing logic

```python
# In handle_inbound(), add near the top:
if user.onboarding_step == "awaiting_intent_response":
    await handle_onboarding_intent_response(user, message_text, telegram_id, db)
    return
```

#### `backend/app/models/user.py` ← MODIFY

Add columns:
```python
onboarding_complete = Column(Boolean, default=False, nullable=False)
onboarding_step = Column(String(50), nullable=True)
```

#### `backend/migrations/versions/xxx_add_onboarding_fields.py` ← CREATE

Alembic migration to add `onboarding_complete` and `onboarding_step` to the `users` table.

---

### 5. Flow Transition After Onboarding

When intent is detected with high confidence, onboarding should hand off cleanly to the existing flow:

```python
async def transition_to_flow(intent: str, user: User, telegram_id: int, 
                              extracted_data: dict, db: AsyncSession):
    # Mark onboarding complete
    user.onboarding_complete = True
    user.onboarding_step = None
    await db.commit()
    
    # Create the job and pre-fill extracted data
    job = Job(user_id=user.id, type=intent, status="collecting")
    job.answers = {
        "_step": "basics",
        "target_role": extracted_data.get("extracted_role"),  # pre-fill if detected
    }
    db.add(job)
    await db.commit()
    
    # Send transition message
    await send_message(telegram_id, f"Great! Let's build your {intent}. I'll guide you step by step.\n\nFirst, what's your full name?")
```

---

### 6. Telegram Message Formatting Guidelines

All onboarding messages should:
- Use the user's first name from Telegram
- Use a warm, encouraging tone
- Use line breaks generously (Telegram renders them well)
- Use emoji sparingly — one per message maximum
- Use Telegram Markdown for italics on examples: `_example text_`
- Never use bullet points in conversational messages
- Keep each message under 300 characters where possible — split into multiple messages if needed

---

### 7. Tests To Write

Create `backend/tests/test_onboarding_flow.py`:

```python
# Test cases to cover:
# 1. New user /start → receives welcome message, onboarding_step set
# 2. High confidence resume intent → job created, flow starts
# 3. High confidence intent with extracted role → role pre-filled in job.answers
# 4. Low confidence intent → soft menu shown
# 5. Returning user /start, no active job → returning user menu
# 6. Returning user /start, active job → continue prompt shown
# 7. User in onboarding_step="awaiting_intent_response" sends unrelated command → still routes to intent handler
# 8. onboarding_complete=True user sends /start → normal returning user flow
```

---

### 8. Edge Cases To Handle

| Scenario | Expected Behaviour |
|---|---|
| User sends `/start` mid-onboarding | Reset onboarding, send welcome again |
| User sends `/help` during onboarding | Answer help, then re-prompt for intent |
| User sends a command like `/status` during onboarding | Handle command normally, then gently re-prompt |
| OpenAI intent detection fails / times out | Fall back to showing the menu silently |
| User's Telegram first_name is unavailable | Use "there" as fallback: "Hey there 👋" |
| Existing users (onboarding_complete=NULL in DB) | Treat as onboarding_complete=True to avoid re-onboarding existing users |

---

### 9. Definition of Done

- [ ] New users receive warm welcome on `/start`
- [ ] Free-text intent response is processed by AI
- [ ] High confidence intent transitions directly to document flow
- [ ] Extracted role/company is pre-filled in `Job.answers` where detected
- [ ] Low confidence shows soft menu
- [ ] Returning users with active jobs see continue prompt
- [ ] Returning users without active jobs see concise menu
- [ ] `onboarding_complete` and `onboarding_step` columns exist and are used correctly
- [ ] Alembic migration created and tested
- [ ] All edge cases handled gracefully
- [ ] Tests written and passing
- [ ] No regression in existing resume/CV/cover letter flows

---

## Summary of Files Changed

| File | Action |
|---|---|
| `backend/app/flows/onboarding.py` | Create new |
| `backend/app/services/ai.py` | Add `detect_onboarding_intent()` |
| `backend/app/services/router.py` | Modify `handle_inbound()` |
| `backend/app/models/user.py` | Add 2 columns |
| `backend/migrations/versions/xxx_add_onboarding_fields.py` | Create migration |
| `backend/tests/test_onboarding_flow.py` | Create tests |
