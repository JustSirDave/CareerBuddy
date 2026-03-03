# CareerBuddy — Pay-Per-Document System

## Stack
FastAPI, PostgreSQL, SQLAlchemy async, Redis, Paystack, python-telegram-bot

## Task
Replace subscription model with pay-per-document credit system.

---

## Pricing
| Product | Price (kobo) | Credits Awarded |
|---|---|---|
| resume | 750000 | +1 document_credit |
| cv | 750000 | +1 document_credit |
| cover_letter | 300000 | +1 cover_letter_credit |
| bundle | 1500000 | +2 document_credits, +1 cover_letter_credit |

---

## 1. models/user.py
REMOVE: `tier`, `generation_count`, `quota_reset_at`, `premium_expires_at`
ADD:
```python
free_resume_used = Column(Boolean, default=False, nullable=False)
free_cover_letter_used = Column(Boolean, default=False, nullable=False)
document_credits = Column(Integer, default=0, nullable=False)
cover_letter_credits = Column(Integer, default=0, nullable=False)
```

## 2. models/payment.py
ADD: `product_type = Column(String(20), nullable=True)`

## 3. services/payments.py — REWRITE

```python
PRICES = {"resume":750000,"cv":750000,"cover_letter":300000,"bundle":1500000}
PRICE_DISPLAY = {"resume":"₦7,500","cv":"₦7,500","cover_letter":"₦3,000","bundle":"₦15,000"}
CREDIT_AWARDS = {
    "resume":       {"document_credits":1,"cover_letter_credits":0},
    "cv":           {"document_credits":1,"cover_letter_credits":0},
    "cover_letter": {"document_credits":0,"cover_letter_credits":1},
    "bundle":       {"document_credits":2,"cover_letter_credits":1},
}

def can_generate_free(user, doc_type) -> bool:
    if doc_type in ("resume","cv"): return not user.free_resume_used
    if doc_type == "cover_letter": return not user.free_cover_letter_used
    return False

def has_paid_credit(user, doc_type) -> bool:
    if doc_type in ("resume","cv"): return user.document_credits > 0
    if doc_type == "cover_letter": return user.cover_letter_credits > 0
    return False

def can_generate(user, doc_type) -> bool:
    return can_generate_free(user, doc_type) or has_paid_credit(user, doc_type)

async def consume_credit(user, doc_type, db) -> str:
    # returns "free" or "paid_credit", raises ValueError if none available
    if can_generate_free(user, doc_type):
        if doc_type in ("resume","cv"): user.free_resume_used = True
        else: user.free_cover_letter_used = True
        await db.commit(); return "free"
    if has_paid_credit(user, doc_type):
        if doc_type in ("resume","cv"): user.document_credits -= 1
        else: user.cover_letter_credits -= 1
        await db.commit(); return "paid_credit"
    raise ValueError(f"No credit for {doc_type}")

async def initiate_payment(user, product_type, db) -> dict:
    # Create Paystack transaction, save pending Payment, return {payment_url, reference}
    # reference format: f"cb_{product_type}_{user.id}_{uuid4().hex[:8]}"
    # amount: PRICES[product_type]
    # metadata: {user_id, telegram_user_id, product_type}
    pass  # implement using existing Paystack pattern in codebase

async def confirm_payment_and_award_credits(reference, db) -> tuple | None:
    # 1. Find Payment by reference — return None if not found or already confirmed
    # 2. Verify with Paystack API
    # 3. Mark payment confirmed
    # 4. Award credits from CREDIT_AWARDS[product_type]
    # 5. Return (user, product_type)
    pass

def get_credit_summary(user) -> str:
    lines = []
    if not user.free_resume_used: lines.append("✓ 1 free resume/CV")
    if not user.free_cover_letter_used: lines.append("✓ 1 free cover letter")
    if user.document_credits > 0: lines.append(f"📄 {user.document_credits} document credit(s)")
    if user.cover_letter_credits > 0: lines.append(f"✉️ {user.cover_letter_credits} cover letter credit(s)")
    return "\n".join(lines) if lines else "No credits remaining."

def get_purchase_prompt(doc_type) -> str:
    if doc_type in ("resume","cv"):
        return (f"You've used your free {doc_type}.\n\n"
                f"Single document — {PRICE_DISPLAY['resume']}\n"
                f"Bundle (2 docs + 1 cover letter) — {PRICE_DISPLAY['bundle']} _save ₦3,000_\n\n"
                f"/buy_{doc_type} or /buy_bundle")
    return (f"You've used your free cover letter.\n\n"
            f"Cover letter — {PRICE_DISPLAY['cover_letter']}\n"
            f"Bundle (2 docs + 1 cover letter) — {PRICE_DISPLAY['bundle']} _save ₦3,000_\n\n"
            f"/buy_cover_letter or /buy_bundle")
```

## 4. services/router.py

REMOVE: all `tier`, `generation_count`, `quota_reset_at`, `premium_expires_at` references, `/upgrade` handler

ADD these command handlers:
```python
# /buy_resume, /buy_cv, /buy_cover_letter, /buy_bundle
# Each: call initiate_payment(user, product_type, db), send payment_url to user

# /status
summary = get_credit_summary(user)
await send_message(telegram_id, f"Your credits:\n\n{summary}")

# Gate all document flows at entry:
if not can_generate(user, doc_type):
    await send_message(telegram_id, get_purchase_prompt(doc_type))
    return

# At document delivery (job → done):
credit_type = await consume_credit(user, doc_type, db)
# if credit_type == "free" → DOCX only
# if credit_type == "paid_credit" → DOCX + PDF
```

## 5. routers/webhook.py — Paystack handler

```python
if event == "charge.success":
    result = await confirm_payment_and_award_credits(reference, db)
    if result:
        user, product_type = result
        credits = CREDIT_AWARDS[product_type]
        # Build credit summary lines and notify user via send_message
        # Trigger referral conversion if first payment:
        if await get_completed_payment_count(user.id, db) == 1:
            await process_referral_conversion(user, db)
```

## 6. Migration

```python
# ADD to users:
# free_resume_used Boolean default false
# free_cover_letter_used Boolean default false
# document_credits Integer default 0
# cover_letter_credits Integer default 0

# Data migration — grace credits for existing premium users:
# UPDATE users SET document_credits=2 WHERE tier='pro' AND premium_expires_at > NOW()

# REMOVE from users: tier, generation_count, quota_reset_at, premium_expires_at

# ADD to payments: product_type String(20) nullable
```

## 7. flows/resume.py
Replace all tier/quota checks at flow entry with:
```python
if not can_generate(user, doc_type): 
    await send_message(telegram_id, get_purchase_prompt(doc_type))
    return
```

## 8. BotFather commands (update manually)
```
buy_resume - Resume ₦7,500
buy_cv - CV ₦7,500
buy_cover_letter - Cover letter ₦3,000
buy_bundle - Bundle 2 docs + cover letter ₦15,000
status - Your credits
```
Remove: `upgrade`

---

## Rules
- Free credit consumed before paid credit always
- Free = DOCX only; Paid = DOCX + PDF
- Duplicate Paystack webhook (same reference) must be idempotent — no double credit
- Bundle = flexible: 2 document_credits spendable on any mix of resume/CV
- Do not break revision, referral, or delivery confirmation flows
