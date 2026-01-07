# 🚀 Telegram Bot Setup Guide - CareerBuddy

## ✅ What We Did

Successfully refactored **CareerBuddy from WhatsApp/WAHA to Telegram Bot API**!

### Changes Made:
- ✅ Removed WAHA Docker service (no more QR codes!)
- ✅ Created `telegram.py` service (replaces `whatsapp.py`)
- ✅ Updated database models (`wa_id` → `telegram_user_id`)
- ✅ Refactored webhook handler for Telegram format
- ✅ Updated all dependencies
- ✅ Cleaned up WhatsApp-specific files
- ✅ Updated README with Telegram instructions

---

## 🎯 Quick Start (5 Minutes)

### Step 1: Create Your Telegram Bot

1. **Open Telegram** and search for `@BotFather`
2. Send the command: `/newbot`
3. Follow prompts:
   - **Bot Name**: `CareerBuddy Bot` (or your choice)
   - **Username**: `your_careerbuddy_bot` (must end with `bot`)
4. **Copy the Bot Token** (looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Update Your .env File

```bash
# Add this to your .env file
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### Step 3: Install Dependencies & Migrate Database

```bash
# Stop current services
docker-compose down

# Rebuild services (to install python-telegram-bot)
docker-compose build

# Start services
docker-compose up -d

# Run the new migration
docker-compose exec api alembic upgrade head
```

### Step 4: Set Up Webhook

#### Option A: For Production (with public domain)

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-domain.com/webhooks/telegram"}'
```

#### Option B: For Local Development (with ngrok)

1. **Install ngrok**: https://ngrok.com/download

2. **Start ngrok**:
```bash
ngrok http 8000
```

3. **Copy the ngrok URL** (e.g., `https://abc123.ngrok.io`)

4. **Set webhook**:
```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://abc123.ngrok.io/webhooks/telegram"}'
```

### Step 5: Verify Setup

```bash
# Check webhook status
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"

# Should return:
# {
#   "ok": true,
#   "result": {
#     "url": "https://your-url.com/webhooks/telegram",
#     "has_custom_certificate": false,
#     "pending_update_count": 0
#   }
# }
```

### Step 6: Test Your Bot!

1. Open Telegram
2. Search for your bot username (e.g., `@your_careerbuddy_bot`)
3. Send: `/start`
4. Bot should reply with the welcome menu!

---

## 🎨 Example Conversation

```
You: /start

Bot: 👋 Hi! I'm Career Buddy, your personal AI assistant...

Choose your plan:
• Free - 2 free documents
• Pay-Per-Generation - ₦7,500 per document

You: Free

Bot: What would you like to create?
• Resume
• CV
• Revamp

You: Resume

... (conversation continues) ...

Bot: ✅ Your resume is ready! [sends DOCX file]
```

---

## 🔥 Why Telegram is Better

| Feature | WhatsApp (WAHA) | Telegram |
|---------|-----------------|----------|
| Setup | QR code scanning, device linking | Bot token from @BotFather (30 seconds) |
| Reliability | Session disconnections | Rock-solid, official API |
| API | Self-hosted WAHA service | Official, free Telegram API |
| File Handling | Complex base64 encoding | Simple multipart upload |
| User IDs | Complex formats (@c.us, @lid) | Simple integer IDs |
| Commands | Text parsing | Native /commands support |
| Maintenance | High (QR rescans, sessions) | Low (set and forget) |

---

## 🐛 Troubleshooting

### Bot Not Responding?

1. **Check webhook**:
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

2. **Check API logs**:
```bash
docker-compose logs api -f
```

3. **Verify bot token in .env**:
```bash
docker-compose exec api env | grep TELEGRAM
```

### Migration Issues?

```bash
# Check current migration version
docker-compose exec api alembic current

# If stuck, view migration history
docker-compose exec api alembic history

# Force upgrade
docker-compose exec api alembic upgrade head
```

### Need to Reset Webhook?

```bash
# Delete webhook
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/deleteWebhook"

# Set new webhook
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -d '{"url": "https://your-new-url.com/webhooks/telegram"}'
```

---

## 📦 What's in the Box

### New Files:
- `backend/app/services/telegram.py` - Telegram Bot API integration
- `backend/migrations/versions/8aa3779ba631_migrate_to_telegram.py` - Database migration

### Modified Files:
- `backend/app/config.py` - Added `telegram_bot_token`
- `backend/app/models/user.py` - Changed to `telegram_user_id` + `telegram_username`
- `backend/app/routers/webhook.py` - Refactored for Telegram updates
- `backend/app/services/router.py` - Updated `handle_inbound()`
- `backend/pyproject.toml` - Added `python-telegram-bot` dependency
- `docker-compose.yml` - Removed WAHA service
- `README.md` - Updated with Telegram instructions

### Removed Files:
- `backend/app/services/whatsapp.py` - No longer needed
- `qr-viewer.html` - No longer needed
- WAHA Docker service and volumes - No longer needed

---

## 🎉 You're All Set!

Your CareerBuddy bot is now running on Telegram - faster, simpler, and more reliable!

**Next Steps:**
1. Share your bot with users
2. Monitor the logs: `docker-compose logs api -f`
3. Enjoy hassle-free bot management! 🚀

---

**Need Help?** Check the main README.md or open an issue on GitHub.

