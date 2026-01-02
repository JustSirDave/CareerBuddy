# CareerBuddy

**AI-powered resume, CV, and cover letter generator** - Create professional career documents through conversational interactions.

## Overview

CareerBuddy is an intelligent agent that helps users create ATS-compliant professional documents through a guided conversation. Currently supports **WhatsApp** as the primary interface, with plans to expand to web.

### Key Features

-  **Conversational Interface** - Natural conversation flow via WhatsApp
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
- **WAHA (WhatsApp HTTP API)** - Self-hosted WhatsApp interface

### Infrastructure
- **Docker & Docker Compose** - Containerization

## Quick Start

### Prerequisites

- Docker & Docker Compose
- WhatsApp number for WAHA (can use personal WhatsApp)
- Anthropic API key (optional, for AI features)

### 1. Environment Setup

Create `.env` file in project root:

```bash
# Application
APP_ENV=local
APP_PORT=8000
LOG_LEVEL=info

# WAHA (WhatsApp HTTP API)
WAHA_URL=http://waha:3000
WAHA_SESSION=default
WAHA_API_KEY=  # Optional, leave empty for development

# Database
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/buddy

# Redis
REDIS_URL=redis://redis:6379/0

# AI/LLM (Optional)
ANTHROPIC_API_KEY=your_anthropic_key_here
OPENAI_API_KEY=your_openai_key_here

# Storage (Optional - files saved locally by default)
S3_ENDPOINT=https://your-endpoint.com
S3_BUCKET=your-bucket
S3_ACCESS_KEY_ID=your_key
S3_SECRET_ACCESS_KEY=your_secret
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

### 5. Connect WhatsApp to WAHA

1. **Get QR Code:**
   ```bash
   # Start a new WhatsApp session
   curl -X POST http://localhost:3000/api/sessions/start \
     -H "Content-Type: application/json" \
     -d '{"name": "default"}'

   # Get the QR code
   curl http://localhost:3000/api/sessions/default/qr
   ```

2. **Scan QR Code:**
   - Open WhatsApp on your phone
   - Go to Settings > Linked Devices
   - Tap "Link a Device"
   - Scan the QR code from the API response

3. **Verify Connection:**
   ```bash
   curl http://localhost:3000/api/sessions/default
   # Should show status: "WORKING"
   ```

4. **Configure Webhook (already set in docker-compose):**
   The webhook is automatically configured to forward messages to your FastAPI backend at `http://api:8000/webhooks/whatsapp`

## Usage

### WhatsApp Conversation Example

```
User: Hi
Bot: What would you like to create? [Resume] [CV] [Cover Letter]

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
Bot:  Your resume is ready!
```

## Architecture

```
WhatsApp ↔ WAHA ↔ FastAPI → AI Enhancement → Document Renderer → Storage
                      ↓
                PostgreSQL + Redis
```

## Database Schema

- **Users** - WhatsApp user data
- **Jobs** - Document creation sessions
- **Messages** - Conversation history
- **Files** - Generated document metadata
- **Payments** - Transaction records (future)

## Development

```bash
cd backend
pip install python-docx anthropic boto3 alembic

# Run locally
uvicorn app.main:app --reload
```

## Project Status

**Phase 2-3: Core Features Complete (60%)**

-  Infrastructure & Database
-  WhatsApp Integration
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
