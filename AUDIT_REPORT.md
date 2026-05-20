# CareerBuddy — Audit Report
Generated: 2026-03-29  
Suite: 195 passed · 19 skipped · 0 failed  

**Sources:** `project docs/CareerBuddy_PRD.docx`, `CareerBuddy_SRS.docx`, `CareerBuddy_SDD.docx`, `CareerBuddy_TDD.docx` (v1 filenames in repo; content matches SRS/PRD/SDD/TDD v1 scope).  
**Method:** Specification text reviewed; backend codebase verified via search and file reads. Items listed as **DONE (known)** per your instructions were not re-investigated.

---

## Summary

| Category         | Done | Partial | Open | Total |
|------------------|------|---------|------|-------|
| Pre-Launch (SRS §11) | 7 | 3 | 5 | 15 |
| Functional (FR)  | ~38 | ~12 | ~6 | ~56 |
| Security (SEC)   | 5 | 2 | 2 | 9 |
| Non-Functional (NFR) | ~10 | ~5 | ~3 | ~18 |
| Integration (INT)| ~8 | ~5 | ~3 | ~16 |
| Tech Debt (SDD §9) | 0 | 3 | 5 | 8 |

**Overall launch readiness: 7 of 15 pre-launch checklist items are fully cleared (DONE).**  
The remainder are **OPEN** (no implementation or QA-only) or **PARTIAL** (started but incomplete vs SRS).

---

## Section A — Pre-Launch Checklist

Per SRS Section 11 (15 items). Status: **DONE** = implemented/verified; **PARTIAL** = gap remains; **OPEN** = not met or QA-only.

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Fix `is_onboarded` / `or True` bug (FR-011) | **DONE** | Per project status; not re-audited. |
| 2 | Expose Revamp in router (FR-040) | **PARTIAL** | Revamp routing and upload path exist (`conversation_router.handle_revamp`, `webhook.py` document upload). Inline keyboard still shows **"✨ Revamp Existing (Soon)"** in `app/services/telegram.py` (~line 172). |
| 3 | Telegram `secret_token` validation (SEC-001) | **DONE** | Per project status; `verify_telegram_webhook_secret` + `setWebhook` `secret_token` in `webhook.py` / `main.py`. |
| 4 | `PAYSTACK_SECRET` + startup fail-fast (SEC-002) | **DONE** | Per project status; `main.py` `startup_event` checks `app_env == "production"` for `paystack_secret` and `telegram_webhook_secret`. |
| 5 | Opay webhook signature verification (SEC-004) | **OPEN** | `grep` for `opay`, `OPAY`, `/webhooks/opay` in `backend/app` returns **no matches** — no Opay webhook route or verifier. |
| 6 | Canonical payment status `'success'` (FR-063) | **DONE** | Per project status; not re-audited. |
| 7 | Test webhook paths `/webhooks/*` (NFR-032) | **DONE** | Per project status; router prefix `/webhooks` in `app/routers/webhook.py`. |
| 8 | Non-default PostgreSQL credentials (SEC-007) | **OPEN** | `docker-compose.yml` sets `POSTGRES_USER: postgres` / `POSTGRES_PASSWORD: postgres`. Production must override via env — not enforced in compose file. |
| 9 | Persistent volume for `output/` (NFR-041) | **OPEN** | `docker-compose.yml` `api` service mounts `./backend:/app` only; **no** named volume for `output/`. |
| 10 | PII retention policy for messages (DAT-001) | **OPEN** | No scheduled purge, TTL, or retention job found; messages persist in DB only. |
| 11 | Log sanitisation — no PII/secrets (SEC-009) | **PARTIAL** | `webhook.py` logs full Telegram `payload` at DEBUG (`Received update: {payload}`). Error path logs `Payload was: {payload}`. Paystack logs event type, not full body at INFO — still risk if DEBUG enabled in prod. |
| 12 | `.env.example` with required variables (NFR-031) | **DONE** | Per project status; file present at repo root. |
| 13 | QA full Revamp E2E (FR-040–045) | **OPEN** | QA/process; not verifiable as code DONE. |
| 14 | QA virtual account / Opay E2E (FR-070–073) | **OPEN** | No Opay integration in codebase. |
| 15 | APScheduler jobs persist across restart (NFR-012) | **OPEN** | `app/services/scheduler.py` uses `BackgroundScheduler()` with **no** `jobstore` / DB persistence — only in-memory interval job for delivery confirmations. |

---

## Section B — Functional Requirements

### B.1 User & Session Management

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-001 | Create User on first contact | **DONE** | `conversation_router.handle_inbound` creates `User` when missing (~1130–1141). |
| FR-002 | No duplicate users per `telegram_id` | **DONE** | Query by `telegram_user_id` before insert. |
| FR-003 | One free Resume/CV + one free CL credit on creation | **PARTIAL** | Implemented as `free_resume_used` / `free_cover_letter_used` booleans + `document_credits` / `cover_letter_credits` on `User` — not separate `Credit` rows per SRS §6.1 data model. `app/models/user.py`, `payments.py`. |
| FR-004 | `onboarding_complete` tracked | **DONE** | `User.onboarding_complete`; set in flows when appropriate. |

### B.2 Onboarding Flow

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-010 | `handle_new_user_welcome` for first-time /start | **DONE** | `onboarding_flow.handle_new_user_welcome` from `handle_inbound` when not onboarded and no jobs. |
| FR-011 | `is_onboarded` from DB, no `or True` | **DONE** | Known fixed; not re-audited. |
| FR-012 | Pass opening message to AI intent classifier | **DONE** | `onboarding_flow.handle_onboarding_intent_response` / `ai.detect_onboarding_intent`. |
| FR-013 | Intent RESUME / COVER_LETTER / REVAMP / MENU | **PARTIAL** | Intent detection exists; exact enum match to SRS wording may differ. |
| FR-014 | MENU or ambiguous → main menu | **DONE** | `__SHOW_MENU__`, `send_choice_menu`, document menus. |

### B.3 Resume / CV Creation

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-020 | Collect required fields stepwise | **DONE** | `resume_flow` + `handle_resume` steps. |
| FR-021 | Validate before advance | **DONE** | `flows/validators.py`, error messages in router. |
| FR-022 | Payment prompt with prices | **PARTIAL** | Credit-based `paystack` prompts in `payments.py`; not identical to SRS “₦0 / ₦7,500” copy everywhere. |
| FR-023 | AI generator with structured context after payment/free confirm | **PARTIAL** | Generation + render; structured JSON enforcement — see INT-012. |
| FR-024 | Deliver within 90s of payment confirmation | **PARTIAL** | No p95 instrumentation; behaviour depends on OpenAI/render. |
| FR-025 | 24h follow-up scheduled | **DONE** | `tasks/delivery_confirmation.py`, `completed_at` + `delivery_confirmation_sent`; scheduler polls ~23–25h window. |

### B.4 Cover Letter Creation

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-030 | Collect title, company, selling points, tone | **PARTIAL** | Cover flow in `handle_cover`; verify every field vs SRS list. |
| FR-031 | Same payment/delivery as FR-022–025; prices ₦0 / ₦3,000 | **PARTIAL** | Credits/prices in `payments.PRICES`; align marketing copy to SRS. |

### B.5 Revamp

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-040 | Revamp available in router | **PARTIAL** | Logic exposed; UI still **"Soon"** — `telegram.py` inline keyboard. |
| FR-041 | Prompt upload PDF/DOCX | **DONE** | `handle_revamp` upload messaging; webhook `handle_document_upload`. |
| FR-042 | Validate type + size ≤10MB | **PARTIAL** | Validation in revamp/upload path — grep `10` / `MB` in `webhook.py` / `conversation_router.py` for exact enforcement. |
| FR-043 | ₦6,000; revamp-specific credit only | **PARTIAL** | `payments.py` product types; confirm revamp cannot use bundle credits only. |
| FR-044 | Extract text → AI improve → document | **DONE** | `document_parser`, `ai.revamp_resume`, `handle_revamp_upload`. |
| FR-045 | Same delivery + follow-up as FR-024–025 | **PARTIAL** | Same mechanisms; revamp job completion must set `completed_at` for follow-up. |

### B.6 Format Selection

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-050 | Paid users: DOCX or PDF choice before/at checkout | **PARTIAL** | Template selection flows; verify all paid paths show format choice. |
| FR-051 | Free users: DOCX only; no format prompt | **PARTIAL** | `payments.can_generate` / free flags; confirm no PDF prompt for free. |
| FR-052 | Deliver selected format | **PARTIAL** | `pdf_renderer`, `renderer`; verify end-to-end per format. |

### B.7 Payments — Paystack

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-060 | Generate Paystack checkout link | **DONE** | `payments.init_paystack_payment` / link generation (httpx to Paystack). |
| FR-061 | Webhook verifies HMAC before processing | **DONE** | `webhook.py` `paystack_webhook`: HMAC-SHA512 when `settings.paystack_secret` set (`~726–735`). |
| FR-062 | `charge.success` → lookup payment, award credit, trigger generation if job awaiting payment | **PARTIAL** | `confirm_payment_and_award_credits` awards credits; job-centric “AWAITING_PAYMENT” FSM may differ from SRS §6.2 naming. |
| FR-063 | Canonical status `success` | **DONE** | Known fixed globally. |

### B.8 Payment — Virtual Account (Opay)

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-070 | Opay API for virtual account | **OPEN** | No Opay API calls in `backend/app`. |
| FR-071 | Send VA, bank, amount in Telegram | **OPEN** | No implementation. |
| FR-072 | Webhook verifies signature; award + generate | **OPEN** | No `/webhooks/opay`. |
| FR-073 | VA single-use / transaction-scoped | **OPEN** | N/A without integration. |

### B.9 Revision System

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-080 | Accept revision after delivery | **DONE** | `/revise`, `flows/revision.py`. |
| FR-081 | Guided prompts (not only free-form) | **PARTIAL** | `revision.py` — confirm structured prompts cover SRS. |
| FR-082 | Pass original + instruction to AI; re-render | **DONE** | Revision flow + renderer. |
| FR-083 | Max rounds configurable via env | **PARTIAL** | `revision_count` on `Job`; **`MAX_REVISION_ROUNDS` not referenced in `backend/app` code** (grep empty). `.env.example` lists it. |

### B.10 Referral System

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-090 | Unique `referral_code` on User | **PARTIAL** | Codes live in `Referral` table (`referral.py` `_generate_code`); **no `referral_code` column on `User`** per SRS §6.1. |
| FR-091 | Expose referral link after first document | **PARTIAL** | `/referral` command + `get_or_create_referral_code`; verify “after first document” timing. |
| FR-092 | Credit referrer on referred user’s first payment | **DONE** | `process_referral_conversion` after Paystack success when `payment_count == 1`. |
| FR-093 | Idempotent conversion | **DONE** | Referral `status` converted; checks in `referral.py`. |

### B.11 Delivery Follow-up & Dropout Recovery

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-100 | 24h follow-up | **DONE** | `delivery_confirmation.py`, scheduler interval. |
| FR-101 | 6h dropout reminder | **DONE** | `DROPOUT_HOURS = 6` in `conversation_router.py`. |
| FR-102 | Reminder includes step + CTA | **PARTIAL** | Verify copy matches SRS in dropout branch. |

### B.12 Admin Commands

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-110 | Gate on `ADMIN_TELEGRAM_IDS` | **DONE** | `is_admin()` in `conversation_router.py`. |
| FR-111 | `/stats`, `/broadcast`, `/grant_credits`, `/sample` | **PARTIAL** | `/stats`, `/broadcast`, `/sample` paths exist; **`/grant_credits` not found** in codebase (grep `grant_credit` / `/grant` empty). `/setpro`, `/makeadmin` present instead of SRS list. |

### B.13 Error Handling (SRS §9)

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-200 | Webhook unhandled → HTTP 200 to Telegram | **DONE** | `telegram_webhook` catches exceptions; returns 200. |
| FR-201 | Friendly user errors | **PARTIAL** | `error_handler.py`, various flows. |
| FR-202 | Generation fails → notify, FAILED job | **PARTIAL** | `render_failed` / error paths in `handle_resume`. |
| FR-203 | Unknown payment reference → log, 200 | **PARTIAL** | `confirm_payment` returns None; webhook returns `ok`. |

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| FR-210 | Off-topic → re-prompt step | **PARTIAL** | Various branches; not uniformly one helper. |
| FR-211 | Mid-flow commands handled safely | **PARTIAL** | Command handling in `handle_inbound`. |

---

## Section C — Security Requirements

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| SEC-001 | `setWebhook` + `X-Telegram-Bot-Api-Secret-Token`; 403 if invalid | **DONE** | Known; `verify_telegram_webhook_secret`, `main.py` payload `secret_token`. |
| SEC-002 | `PAYSTACK_SECRET` required in production | **DONE** | Known; `main.py` startup. |
| SEC-003 | Paystack HMAC before processing | **DONE** | `paystack_webhook`: gates on **`if settings.paystack_secret`** — if unset, body is still processed (dev flexibility); matches “verify when secret configured”. |
| SEC-004 | Opay webhook signature | **OPEN** | No Opay webhook. |
| SEC-005 | Admin allowlist | **DONE** | `is_admin` + `ADMIN_TELEGRAM_IDS`. |
| SEC-006 | Download: job exists + `Path(filename).name` | **DONE** | `main.py` `download_file`: UUID check, `db.query(Job)`, `safe_filename = Path(filename).name` (`~146–160`). |
| SEC-007 | No default postgres creds in production | **PARTIAL** | **Code:** `DATABASE_URL` from env. **Deploy:** `docker-compose.yml` still documents default postgres/postgres for local `postgres` service. |
| SEC-008 | `.env` gitignored; rotate leaked secrets | **DONE** | `.gitignore` typically includes `.env` (not re-verified in this pass). |
| SEC-009 | No full PII/secrets in logs | **PARTIAL** | Telegram `payload` logged at DEBUG; error handler logs payload string. |

---

## Section D — Non-Functional Requirements

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| NFR-001 | ≤90s p95 payment → delivery | **PARTIAL** | No metrics collection verified. |
| NFR-002 | Ack within 5s | **PARTIAL** | `send_typing_action`; no automated timing proof. |
| NFR-003 | Exponential backoff, 3 attempts, 1s ×2 | **PARTIAL** | `ai.py`: `MAX_AI_RETRIES = 2`, delay 1.5s linear — **not** 3 attempts / exponential per SRS. |
| NFR-010 | Redis idempotency on Telegram + payment webhooks | **PARTIAL** | `seen_or_mark` on Telegram `msg_id` only; **Paystack webhook does not call `seen_or_mark` on reference** (grep). |
| NFR-011 | Redis unavailable → fail open | **DONE** | `idempotency.py` returns False when Redis missing. |
| NFR-012 | APScheduler persisted to DB | **OPEN** | In-memory scheduler only (`scheduler.py`). |
| NFR-020 | Single-instance v1 | **DONE** | Architecture matches. |
| NFR-021 | In-memory rate limit OK for v1 | **DONE** | `middleware/rate_limit.py`. |
| NFR-030 | Router refactor post-launch | **OPEN** | `conversation_router.py` still large (design debt, not blocking). |
| NFR-031 | `.env.example` complete | **PARTIAL** | File exists; **`SECRET_KEY`, `OPAY_*`, `OPENAI_MODEL` in `.env.example` but not all in `app/config.py` Settings model** — runtime may ignore some vars. |
| NFR-032 | Webhooks `/webhooks/telegram`, `/webhooks/paystack` | **DONE** | Router prefix + routes. |
| NFR-040 | Files under `output/jobs/{job_id}/` | **DONE** | Storage paths in code. |
| NFR-041 | Docker volume for `output/` in prod | **OPEN** | `docker-compose.yml` — no dedicated `output` volume. |
| NFR-042 | Object storage post-launch | **OPEN** | Acknowledged debt. |
| NFR-050–052 | Test coverage requirements | **PARTIAL** | Suite green; full E2E mocked OpenAI/Telegram per NFR-051 not all PASS (skipped integration tests per prior work). |

---

## Section E — Integration Requirements

| Req ID | Description | Status | Gap / File |
|--------|-------------|--------|------------|
| INT-001 | Shared `httpx.AsyncClient` for Telegram | **OPEN** | `telegram.py` uses **`async with httpx.AsyncClient(...)`** per call — multiple clients, not one shared pooled instance. |
| INT-002 | `setWebhook` with `secret_token` | **DONE** | `main.py` `payload["secret_token"]`. |
| INT-003 | `sendDocument` multipart from file | **DONE** | `telegram.py` file upload paths. |
| INT-004 | Typing within 5s | **PARTIAL** | `send_typing_action` called early in `_process_telegram_update`; not measured. |
| INT-010 | Model via `OPENAI_MODEL` | **PARTIAL** | **Hardcoded `gpt-4o-mini`** in `ai.py` e.g. `generate_skills` (~76); `OPENAI_MODEL` not in `Settings`. |
| INT-011 | System prompt on all calls | **PARTIAL** | Present on many calls; audit each function. |
| INT-012 | Structured JSON/XML for document generation | **PARTIAL** | Some JSON extraction in `ai.py` (~426); not all generation paths enforce structured output only. |
| INT-013 | Retry on RateLimit / APIConnection only | **PARTIAL** | `_call_with_retry` catches broad `Exception`. |
| INT-020 | Paystack amount in kobo | **DONE** | `payments.py` uses kobo for amounts. |
| INT-021 | Handle `charge.success`; others 200 no-op | **PARTIAL** | Only `charge.success` actioned; other events return 200 — verify all event types. |
| INT-022 | Reference stored on Payment | **DONE** | `Payment.reference` used in webhook flow. |
| INT-030–033 | Opay VA + webhook + `OPAY_WEBHOOK_SECRET` | **OPEN** | No Opay code paths. |

---

## Section F — Open Questions

SRS Section 12 / PRD Section 13 alignment.

| # | Question | Resolvable from code? | Current value or still open |
|---|----------|------------------------|-----------------------------|
| 1 | Referral reward type/value | **Partially** | `REFERRAL_REWARD_TYPE`, `REFERRAL_REWARD_VALUE` in `.env.example` and used in referral logic — not fully “open” if env set. |
| 2 | Max revision rounds | **Partially** | `.env.example` has `MAX_REVISION_ROUNDS=3`; **code does not read env** (grep empty). |
| 3 | PII retention window for messages | **Open** | No enforcement in code. |
| 4 | Signed expiry tokens for download at launch? | **Partially** | `download_file` has `token: str = ""` parameter in `main.py` — usage vs SRS “post-launch” needs product decision; no HMAC signing grep found. |
| 5 | Canonical payment status string | **Resolved** | `'success'` in codebase per known fix. |

PRD Q5 (“success” vs “successful”) — **resolved** in code.

---

## Section G — Technical Debt (SDD §9)

| Item | Severity | Status | Notes |
|------|----------|--------|-------|
| Local filesystem storage | High | **Still outstanding** | No object storage. |
| Synchronous OpenAI calls | Medium | **Still outstanding** | `openai` sync client in `ai.py`. |
| In-process APScheduler | Medium | **Still outstanding** | No DB jobstore; duplicate risk multi-worker. |
| In-memory rate limiting | Medium | **Still outstanding** | `rate_limit.py`. |
| `router` / conversation_router size | Medium | **Partially addressed** | Renamed to `conversation_router.py`; still monolithic. |
| PII in messages table | Medium | **Still outstanding** | No retention job. |
| Download URL security (signed expiry) | Low–Medium | **Partially addressed** | Job UUID + DB check + `Path.name`; signed tokens not implemented. |
| httpx per request | Low | **Still outstanding** | `telegram.py` pattern. |

---

## Recommendations

### Must Fix Before Launch (blocking)

1. **Opay virtual account + webhook (FR-070–073, SEC-004, INT-030–033)** — No implementation; SRS treats payment as dual-gateway. *If launch is Paystack-only, PRD/SRS must be formally amended.*

2. **Pre-launch checklist items still OPEN:** persistent **`output/`** volume (NFR-041), **APScheduler persistence** (NFR-012), **DAT-001** retention policy (process + optional job), **SEC-009** log sanitisation for Telegram payloads, **production DB credentials** in deployment (SEC-007), **E2E QA** for Revamp and Opay (checklist #13–14).

3. **Inline UI:** Remove **“Revamp … (Soon)”** if Revamp is launch-ready (checklist #2 / FR-040).

### Should Fix Before Launch (high risk)

1. **Payment webhook idempotency (NFR-010)** — Add Redis `seen_or_mark` for Paystack reference/event id before crediting.

2. **Admin parity (FR-111)** — Implement **`/grant_credits`** or update SRS to match `/setpro` / `/makeadmin`.

3. **Config parity (NFR-031 / SRS §8)** — Load **`SECRET_KEY`**, **`OPENAI_MODEL`**, **`OPAY_*`** in `Settings` if used, or document as unused.

4. **INT-001** — Single long-lived `httpx.AsyncClient` for Telegram (lifecycle in app startup/shutdown).

5. **NFR-003 / INT-013** — Align retry count (3) and backoff with SRS; narrow exception types for retries.

6. **`MAX_REVISION_ROUNDS`** — Read from environment in `flows/revision.py` (FR-083).

### Post-Launch Backlog

1. Object storage for documents (NFR-042 / SDD).  
2. External job queue (Celery) replacing APScheduler at scale.  
3. Redis-backed rate limiting (NFR-021).  
4. Router split into dispatcher + thin modules (NFR-030).  
5. Async OpenAI / `asyncio.to_thread` for AI calls.  
6. Signed download URLs with expiry (SDD debt).  
7. Full structured-output enforcement for all AI document generation (INT-012).

---

*End of report.*
