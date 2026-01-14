# CareerBuddy

**AI-powered resume, CV, and cover letter generator** - Create professional career documents through conversational interactions.

## Overview

CareerBuddy is an intelligent agent that helps users create ATS-compliant professional documents through a guided conversation. Currently supports **Telegram** as the primary interface, with plans to expand to web.

### Key Features

-  **Conversational Interface** - Natural conversation flow via Telegram
-  **AI-Enhanced Content** - OpenAI GPT-4 generates summaries and skills
-  **ATS-Compliant** - Documents follow applicant tracking system best practices
-  **Multi-Document Support** - Resume, CV, and cover letter generation
-  **Smart Parsing** - Handles comma-separated input for quick data entry
-  **Auto-Generation** - AI drafts professional summaries and suggests skills
-  **Multi-Experience Support** - Add multiple work experiences and education
-  **Deduplication** - Prevents double-processing of messages
-  **Premium Tier** - Monthly subscription (₦7,500) with auto-renewal and quota system
-  **PDF Export** - Direct PDF generation with pixel-perfect layouts
-  **Multiple Templates** - 3 professional templates (Classic, Modern, Executive)
-  **Admin Privileges** - Unlimited access for testing and development (configured via .env)

## Tech Stack

### Backend
- **FastAPI** - Modern async Python web framework
- **PostgreSQL 16** - Primary database
- **Redis 7** - Caching and idempotency
- **SQLAlchemy 2.0** - ORM with migrations (Alembic)

### Document Generation
- **python-docx** - DOCX file generation
- **ReportLab** - Direct PDF generation (all templates)
- **LibreOffice** - DOCX to PDF conversion for user-edited files

### AI/LLM
- **OpenAI GPT-4** - Skills generation and content enhancement

### External APIs
- **Telegram Bot API** - Official Telegram bot interface
- **Paystack API** - Payment processing

### Infrastructure
- **Docker & Docker Compose** - Containerization

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Telegram Bot Token (get from @BotFather on Telegram)
- OpenAI API key (optional, for AI features)

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

# AI/LLM (Optional - for skills/summary generation)
OPENAI_API_KEY=your_openai_key_here

# Payments (Paystack - Optional)
PAYSTACK_SECRET=your_paystack_secret_here

# Admin (Optional - comma-separated Telegram user IDs for unlimited access)
ADMIN_TELEGRAM_IDS=123456789,987654321
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
Bot: What's your target role?

User: Senior Backend Engineer
Bot: [AI generates skills] Select 5-8 skills by number...

User: 1, 2, 3, 4, 5
Bot: Share your work experience...

User: Backend Engineer, TechCorp, NYC, Jan 2020, Present
Bot: Send 2-4 bullets. Type 'done' when finished.

User: Built API serving 1M+ requests/day
User: Reduced query time by 60%
User: done
Bot:  Your resume is ready! [Document sent]

User: /pdf
Bot: ⚙️ Generating PDF... [PDF sent]
```

### Available Commands

- `/start` - Begin or restart
- `/help` - Show help guide
- `/status` - Check your account status
- `/upgrade` - Upgrade to Premium (₦7,500/month)
- `/pdf` - Convert document to PDF (Premium only)
- `/reset` - Cancel current job and start over

## Premium Features

Upgrade to Premium for ₦7,500/month:

### Free Tier
-  **1 Resume** per month
-  **1 CV** per month
-  **1 Revamp** per month
-  **DOCX format** only
-  ❌ No Cover Letters
-  ❌ No PDF conversion

### Premium Tier (₦7,500/month)
-  **2 Resumes** per month
-  **2 CVs** per month
-  **1 Cover Letter** per month
-  **1 Revamp** per month
-  **PDF + DOCX** format
-  **3 Professional Templates**
-  **Auto-renewal** every 30 days

Type `/upgrade` in the bot to get started!

## Admin Privileges

For testing and development, admin users get **unlimited access** to all features:

-  **∞ Unlimited Documents** - Create as many documents as you want
-  **All Document Types** - Resume, CV, Cover Letter, Revamp
-  **PDF Always Enabled** - No restrictions
-  **No Quota Tracking** - Admin generations not counted
-  **Never Expires** - Permanent unlimited access

**Setup:**
1. Get your Telegram User ID from `@userinfobot`
2. Add to `.env` file: `ADMIN_TELEGRAM_IDS=your_telegram_id`
3. Restart the bot
4. Type `/status` to verify admin access

See [ADMIN_PRIVILEGES.md](ADMIN_PRIVILEGES.md) for full details.

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
- **Payments** - Transaction records (Paystack integration)

## Development

```bash
cd backend

# Install dependencies
poetry install

# Run locally (with hot reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest

# Format code
black app/
isort app/
```

## Project Status

**Phase 3: Core Features Complete (90%)**

-  ✅ Infrastructure & Database
-  ✅ Telegram Integration
-  ✅ Resume/CV Flow
-  ✅ Document Rendering (DOCX + PDF)
-  ✅ AI Enhancement
-  ✅ Cover Letter Flow
-  ✅ Payment Integration (Paystack)
-  ✅ Premium Tier System
-  ✅ PDF Direct Generation (ReportLab)
-  🔄 Web Interface (Planned)

## License

MIT License

---

## 👨‍💻 Author

**Sir Dave**  
GitHub: [@JustSirDave](https://github.com/JustSirDave)

---

**Made for job seekers everywhere**
