# CareerBuddy

AI-powered career document assistant. Telegram-native.

## What It Does

CareerBuddy helps job seekers create professional Resumes, CVs, Cover Letters,
and revamp existing documents through a guided Telegram conversation.

## Stack

- FastAPI + PostgreSQL + Redis
- OpenAI GPT-4
- Paystack + Opay virtual accounts
- python-docx + LibreOffice (PDF)
- Telegram Bot API

## Documentation

All design and requirements documents are in `project docs/`:

- PRD — product requirements
- SRS — software requirements specification
- SDD — software design document
- TDD — technical design document (this cleanup)

## Setup

1. Copy `.env.example` to `.env` and fill all values
2. `docker-compose up --build`
3. Run migrations: `docker compose exec api alembic upgrade head`
4. Set Telegram webhook: startup does this automatically when `PUBLIC_URL` is public

## Pre-Launch Checklist

See `DEPLOYMENT_CHECKLIST.md` and SRS Section 11.
