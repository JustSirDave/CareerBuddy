# CareerBuddy — Project Overview

**Author:** Sir Dave  
**Last Updated:** March 2026

---

## 1. Executive Summary

**CareerBuddy** is an AI-powered career document assistant that helps users create ATS-compliant resumes, CVs, and cover letters through a conversational interface. The primary interface is **Telegram**, where users chat with the bot, answer guided questions, and receive professionally formatted documents (DOCX and PDF).

The project automates what was traditionally a freelance service: interviewing users, structuring their information, and producing polished career documents. It is open source and designed for self-hosting or deployment.

---

## 2. Vision & Scope

### 2.1 Core Value Proposition

- **For job seekers:** Create professional documents in 5–10 minutes via chat, with AI enhancement.
- **For developers:** Learn conversational AI flows, document generation, payment integration, and production Python architecture.
- **For the creator:** Automate a repetitive freelance service and share the solution openly.

### 2.2 In-Scope

| Area | Description |
|------|-------------|
| **Document Types** | Resume, CV, Cover Letter |
| **Interface** | Telegram (primary) |
| **AI Features** | Skills suggestions, professional summary generation |
| **Output Formats** | DOCX, PDF |
| **Monetization** | Free tier + Premium (₦7,500/month) via Paystack |
| **Templates** | 3 professional designs (Classic, Modern, Executive) |
| **Admin Tools** | Unlimited access for configured Telegram IDs |

### 2.3 Out-of-Scope / Planned

| Feature | Status |
|---------|--------|
| **Revamp** (upload existing doc for AI improvement) | Coming Soon |
| **Pay-per-document** | Coming Soon |
| **Web interface** | Planned |
| **WhatsApp** | Legacy (WAHA references remain in config) |

---

## 3. Architecture

### 3.1 High-Level Flow

```
┌─────────────┐     ┌──────────────────────────────────────────────────────────┐
│  Telegram   │────▶│  FastAPI (webhook)  │  Router  │  AI  │  Renderer  │ DB  │
│   Users     │◀────│  /webhooks/telegram │  Logic   │ GPT  │  DOCX/PDF   │     │
└─────────────┘     └──────────────────────────────────────────────────────────┘
                              │                    │
                              ▼                    ▼
                    ┌─────────────┐        ┌─────────────────┐
                    │   Redis     │        │   PostgreSQL   │
                    │ Idempotency │        │ Users, Jobs,  │
                    │ Rate Limit  │        │ Messages,      │
                    └─────────────┘        │ Payments      │
                                           └─────────────────┘
```

### 3.2 Component Overview

| Component | Technology | Role |
|-----------|------------|------|
| **API** | FastAPI | Web server, webhook handler, routing |
| **Router** | Custom (`router.py`) | Conversation state machine, step logic |
| **Flows** | `flows/resume.py`, etc. | Questions, parsers, validators |
| **AI** | OpenAI GPT-4 | Skills, summaries, content enhancement |
| **Renderer** | python-docx, ReportLab | DOCX and PDF generation |
| **Storage** | Local filesystem | `output/jobs/{job_id}/` |
| **Database** | PostgreSQL 16 | Users, jobs, messages, payments |
| **Cache** | Redis 7 | Idempotency, rate limiting |

### 3.3 Request Flow (Telegram Message)

1. **Telegram** sends update to `POST /webhooks/telegram`
2. **Webhook** parses payload, checks for duplicates (Redis)
3. **Router** (`handle_inbound`) determines context:
   - Global commands: `/start`, `/help`, `/status`, etc.
   - Active job: continue current flow (resume, CV, cover letter)
   - New intent: infer document type or show menu
4. **Flow handler** (e.g. `handle_resume`) processes step, updates `Job.answers`
5. **AI service** (when needed) calls OpenAI for skills/summary
6. **Renderer** generates DOCX (and optionally PDF)
7. **Telegram service** sends reply or document to user

---

## 4. Design Decisions

### 4.1 Conversation Model

- **Stateful:** Each user has at most one active `Job` (status: `collecting`, `preview_ready`, etc.)
- **Step-based:** Answers stored in `Job.answers` JSON; `_step` drives the flow
- **Idempotent:** Redis tracks `msg_id` to avoid duplicate processing
- **Wake words:** "continue", "ready", "show" trigger AI generation or re-display of AI content

### 4.2 Document Generation

- **Templates:** 3 designs (Classic, Modern, Executive) for resume/CV
- **DOCX:** python-docx for structure and styling
- **PDF:** ReportLab for direct PDF; LibreOffice as fallback for edited DOCX
- **Storage:** Local `output/jobs/{job_id}/{filename}`; download via `/download/{job_id}/{filename}`

### 4.3 Payment & Tiers

- **Free:** 1 resume, 1 CV, 1 revamp/month; DOCX only; no cover letter
- **Premium (₦7,500/month):** 2 resumes, 2 CVs, 1 cover letter, 1 revamp; PDF + DOCX
- **Admin:** Unlimited (bypasses all checks) via `ADMIN_TELEGRAM_IDS`
- **Tracking:** `generation_count` JSON per document type; `quota_reset_at`, `premium_expires_at` for resets and expiry

### 4.4 Webhook Strategy

- **Auto-registration:** On startup, if `PUBLIC_URL` is not localhost, the app calls Telegram `setWebhook`
- **Local dev:** Use ngrok; set `PUBLIC_URL` to ngrok HTTPS URL
- **Paystack:** Webhook at `/webhooks/paystack` for payment confirmation

---

## 5. Data Model

### 5.1 Core Entities

```
User
├── id, telegram_user_id, telegram_username
├── tier (free | pro)
├── generation_count (JSON: {resume, cv, cover_letter, revamp})
├── quota_reset_at, premium_expires_at
└── jobs, messages, payments

Job
├── id, user_id, type (resume | cv | cover_letter)
├── status (collecting | preview_ready | done | ...)
├── answers (JSON: _step, basics, experiences, skills, summary, ...)
├── last_msg_id (deduplication)
└── messages, payments

Message
├── id, job_id, role (user | assistant), content
└── (conversation history)

Payment
├── id, user_id, reference, amount, status
├── raw_webhook (Paystack payload)
└── metadata
```

### 5.2 Job Status Flow

```
collecting → draft_ready → preview_ready → [payment_required] → done
                                    ↓
                            (Premium: skip payment)
```

---

## 6. Project Structure

```
CareerBuddy/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, startup, webhook registration
│   │   ├── config.py            # Settings from env
│   │   ├── db.py                # SQLAlchemy engine, session
│   │   ├── models/              # User, Job, Message, Payment
│   │   ├── routers/
│   │   │   └── webhook.py       # Telegram + Paystack webhooks
│   │   ├── services/
│   │   │   ├── router.py        # Conversation routing (handle_inbound)
│   │   │   ├── ai.py            # OpenAI integration
│   │   │   ├── renderer.py      # DOCX generation
│   │   │   ├── pdf_renderer.py  # PDF generation (ReportLab)
│   │   │   ├── storage.py       # File save, DOCX→PDF
│   │   │   ├── telegram.py      # Send messages, documents, menus
│   │   │   ├── payments.py     # Quota, tiers, Paystack
│   │   │   ├── idempotency.py  # Redis deduplication
│   │   │   └── document_parser.py  # DOCX/PDF extraction (revamp)
│   │   ├── flows/
│   │   │   └── resume.py        # Questions, parsers, validators
│   │   └── middleware/          # Rate limiting
│   ├── migrations/              # Alembic
│   ├── tests/                   # pytest (275+ tests)
│   └── pyproject.toml
├── docker-compose.yml           # api, postgres, redis
├── .env                         # Configuration (not committed)
└── output/jobs/                # Generated documents (local)
```

---

## 7. Key Flows

### 7.1 Resume/CV Flow

1. **basics** — Name, email, phone, location (comma-separated)
2. **target_role** — Job title applying for
3. **experiences** — Role, company, city, dates (repeat or "done")
4. **experience_bullets** — 2–4 achievement bullets per role
5. **skills** — AI suggests; user selects by number or types custom
6. **summary** — AI generates; user confirms or edits (wake word: "continue")
7. **education** — Degree, institution, year
8. **certifications** — Optional
9. **profiles** — LinkedIn, GitHub, etc.
10. **projects** — Optional
11. **preview** — Review; confirm to generate
12. **finalize** — Render DOCX, send to user

### 7.2 Cover Letter Flow

1. **basics** — Same as resume
2. **role_company** — Target role and company
3. **highlights** — Key points to emphasize
4. **preview** → **finalize**

### 7.3 Commands

| Command | Description |
|--------|-------------|
| `/start` | Welcome, show document type menu |
| `/help` | Help guide |
| `/status` | Quota, tier, reset/expiry dates |
| `/upgrade` | Paystack payment link |
| `/pdf` | Convert last document to PDF (Premium) |
| `/reset` | Cancel current job |
| `/admin`, `/stats`, `/broadcast` | Admin-only |

---

## 8. Testing & Quality

- **Framework:** pytest, pytest-asyncio, pytest-cov
- **Layers:** Unit (models, services), API (webhooks), integration (full flows)
- **Coverage:** ~83% for critical paths
- **Fixtures:** In-memory SQLite for tests; mocks for OpenAI, Telegram, Paystack

---

## 9. Deployment

- **Containers:** Docker Compose (api, postgres, redis)
- **Env:** `TELEGRAM_BOT_TOKEN`, `PUBLIC_URL`, `OPENAI_API_KEY`, `PAYSTACK_SECRET`, `DATABASE_URL`, `REDIS_URL`
- **Webhook:** Auto-set when `PUBLIC_URL` is public; manual curl otherwise
- **Migrations:** `alembic upgrade head`

---

## 10. Summary

CareerBuddy is a production-ready, Telegram-first AI assistant for creating career documents. It combines conversational flows, AI enhancement, document rendering, and a tiered payment system. The architecture is modular, testable, and suitable for self-hosting or deployment with minimal configuration.
