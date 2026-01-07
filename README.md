# CareerBuddy

**AI-powered resume, CV, and cover letter generator** - Create professional career documents through conversational interactions.

## Overview

CareerBuddy is an intelligent agent that helps users create ATS-compliant professional documents through a guided conversation. Currently supports **Telegram** as the primary interface, with plans to expand to web.

### Key Features

-  **Conversational Interface** - Natural conversation flow via Telegram
-  **AI-Enhanced Content** - Claude AI improves summaries and bullet points
-  **ATS-Compliant** - Documents follow applicant tracking system best practices
-  **Multi-Document Support** - Resume, CV, and cover letter generation
-  **Smart Parsing** - Handles comma-separated input for quick data entry
-  **Auto-Generation** - AI drafts professional summaries if user skips
-  **Multi-Experience Support** - Add multiple work experiences and education
-  **Deduplication** - Prevents double-processing of messages

## Tech Stack

### Backend
- **FastAPI** - Modern async Python web framework
- **PostgreSQL 16** - Primary database
- **Redis 7** - Caching and message broker
- **SQLAlchemy 2.0** - ORM with async support
- **Alembic** - Database migrations
- **Celery 5.4** - Background task queue

### Document Generation
- **python-docx** - DOCX file generation
- **Jinja2** - Template engine

### AI/LLM
- **Anthropic Claude** - Content enhancement and generation

### Storage
- **boto3** - S3/Cloudflare R2 integration

### External APIs
- **Telegram Bot API** - Official Telegram bot interface

### Infrastructure
- **Docker & Docker Compose** - Containerization

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Telegram Bot Token (get from @BotFather on Telegram)
- Anthropic API key (optional, for AI features)

### 1. Environment Setup

Create `.env` file in project root:

```bash
# Application
APP_ENV=local
APP_PORT=8000
LOG_LEVEL=info
PUBLIC_URL=http://localhost:8000

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/buddy

# Redis
REDIS_URL=redis://redis:6379/0

# AI/LLM (Optional)
ANTHROPIC_API_KEY=your_anthropic_key_here
OPENAI_API_KEY=your_openai_key_here

# Payments (Paystack - Optional)
PAYSTACK_SECRET=your_paystack_secret_here

# Storage (S3 - Optional, files saved locally by default)
S3_ENDPOINT=
S3_REGION=
S3_BUCKET=
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
```

### 2. Start Services

```bash
docker-compose up -d
```

### 3. Run Migrations

```bash
docker-compose exec api alembic upgrade head
```

### 4. Verify Setup

```bash
curl http://localhost:8000/health
# Response: {"status": "ok", "env": "local"}
```

### 5. Create Telegram Bot

1. **Get Bot Token from @BotFather:**
   - Open Telegram and search for `@BotFather`
   - Send `/newbot` command
   - Follow the prompts to name your bot
   - Copy the bot token provided

2. **Add Token to .env:**
   ```bash
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

3. **Set Webhook:**
   ```bash
   curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://your-public-domain.com/webhooks/telegram"}'
   ```
   
   For local development with ngrok:
   ```bash
   # Install ngrok and run
   ngrok http 8000
   
   # Use the ngrok URL for webhook
   curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://your-ngrok-url.ngrok.io/webhooks/telegram"}'
   ```

4. **Verify Webhook:**
   ```bash
   curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
   ```

## Usage

### Telegram Conversation Example

```
User: /start
Bot: 👋 Hi! Choose your plan: Free or Pay-Per-Generation

User: Resume
Bot: Send your details (comma-separated):
     Full Name, Title, Email, Phone, City Country

User: John Doe, Backend Engineer, john@example.com, +1234, NYC USA
Bot: Share a professional summary or type 'skip'

User: skip
Bot: List your skills (comma-separated)

User: Python, FastAPI, PostgreSQL, Docker
Bot: Send: Role, Company, City, Start, End

User: Backend Engineer, TechCorp, NYC, Jan 2020, Present
Bot: Send 2-4 bullets. Type 'done' when finished.

User: Built API serving 1M+ requests/day
User: Reduced query time by 60%
User: done
Bot:  Your resume is ready! [Document sent]
```

## Architecture

```
Telegram ↔ FastAPI → AI Enhancement → Document Renderer → Storage
             ↓
       PostgreSQL + Redis
```

## Database Schema

- **Users** - Telegram user data (telegram_user_id, username, tier)
- **Jobs** - Document creation sessions
- **Messages** - Conversation history
- **Files** - Generated document metadata
- **Payments** - Transaction records (Paystack integration)

## Development

```bash
cd backend
pip install python-docx anthropic boto3 alembic

# Run locally
uvicorn app.main:app --reload
```

## Project Status

**Phase 2-3: Core Features Complete (70%)**

-  Infrastructure & Database
-  Telegram Integration
-  Resume/CV Flow
-  Document Rendering
-  AI Enhancement
- � Cover Letter Flow
- � Web Interface
- � Payment Integration

## License

MIT License

---

**Made for job seekers everywhere**
