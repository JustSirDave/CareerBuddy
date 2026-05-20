# CareerBuddy — Runbook

Operational reference for deployed instances. Assumes Railway hosting.

---

## Deployments

### Trigger a redeploy

Railway redeploys automatically on every push to `main`. To force a redeploy without a code change:

> Railway dashboard → your service → **Deployments** tab → click **Redeploy** on the latest deployment.

Or via CLI:
```bash
railway up
```

### Roll back to a previous deployment

> Railway dashboard → your service → **Deployments** tab → find the deployment you want → click **Rollback**.

Railway will instantly serve the previous image. No data is lost (database is unchanged).

### Run migrations manually

SSH into the running container via Railway CLI:
```bash
railway run alembic upgrade head
```

Or exec into the container:
```bash
railway shell
# inside the shell:
alembic upgrade head
```

To check the current migration version:
```bash
railway run alembic current
```

To see pending migrations:
```bash
railway run alembic heads
```

---

## Checking Health

### Railway logs

> Railway dashboard → your service → **Logs** tab.

What to look for:
- `[BOOT] Telegram webhook set: https://...` — webhook registered successfully at startup
- `[BOOT] Missing required env: TELEGRAM_BOT_TOKEN` — a required variable is unset
- `[telegram_webhook]` lines — normal request handling
- `ERROR` lines — exceptions that need investigation
- `alembic.runtime.migration` — migration output at startup

### Health endpoint

```
GET /health
```

Healthy response:
```json
{"status": "ok", "env": "production"}
```

If the service is unreachable or returning 5xx, check Railway logs immediately.

Database health check (requires a live DB connection):
```
GET /health/db
```

### Sentry

Error tracking dashboard: *(add your Sentry project URL here)*

---

## Common Failures and Fixes

| Symptom | Likely Cause | Fix |
|---|---|---|
| Bot not responding to messages | Process crashed or webhook not set | Check Railway logs; if crashed redeploy; if running check `[BOOT] Telegram webhook set` log line |
| "Table does not exist" on startup | Migration not run | `railway run alembic upgrade head` |
| Documents not delivering to users | Cloudinary misconfigured | Verify `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` are set in Railway env vars |
| OpenAI errors in logs | API key invalid or quota exceeded | Check `OPENAI_API_KEY`; check usage at platform.openai.com |
| Webhook not receiving updates | Wrong webhook URL registered | Re-deploy (startup auto-registers webhook) or call Telegram's `setWebhook` manually with the correct `PUBLIC_URL` |
| Redis connection errors | Redis service down | Railway dashboard → Redis plugin → check status; restart if needed |
| `alembic_version` errors on startup | Migration chain broken | Check `alembic current` and `alembic heads`; apply missing migrations |
| Docker build fails: disk space | apt cache overflow | Check Dockerfile — LibreOffice is installed in two separate RUN layers to stay within apt archive limits |

---

## User Operations

### Reset a stuck user conversation

Clears the active job so the user can start fresh:

```sql
-- Find the user
SELECT id, telegram_user_id, name FROM users WHERE telegram_user_id = '<telegram_id>';

-- Cancel their in-progress job(s)
UPDATE jobs
SET status = 'cancelled'
WHERE user_id = '<user_uuid>'
  AND status IN ('collecting', 'preview_ready', 'render_failed');
```

The next message the user sends will route them to the main menu.

### Check a user's monthly usage

```sql
SELECT
    u.telegram_user_id,
    u.name,
    u.monthly_doc_count,
    u.monthly_reset_date
FROM users u
WHERE u.telegram_user_id = '<telegram_id>';
```

To manually reset a user's monthly count:
```sql
UPDATE users
SET monthly_doc_count = 0, monthly_reset_date = CURRENT_DATE
WHERE telegram_user_id = '<telegram_id>';
```

### View recent jobs for a user

```sql
SELECT j.id, j.type, j.status, j.created_at, j.completed_at
FROM jobs j
JOIN users u ON u.id = j.user_id
WHERE u.telegram_user_id = '<telegram_id>'
ORDER BY j.created_at DESC
LIMIT 10;
```

### Manually trigger a redeployment

```bash
# Via Railway CLI
railway up

# Or push an empty commit to main
git commit --allow-empty -m "chore: trigger redeploy" && git push
```

---

## Emergency

### Take the bot offline immediately

> Railway dashboard → your service → **Settings** → **Domains** → remove the domain.

Telegram will stop being able to reach the webhook. Users will see "bot is offline" or messages will silently queue.

### Restore after taking offline

1. Re-add the domain in Railway settings.
2. Wait for the service to become healthy (`/health` returns `200`).
3. The webhook is re-registered automatically on the next startup. Alternatively, call Telegram manually:
   ```bash
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://<your-domain>/webhooks/telegram", "secret_token": "<TELEGRAM_WEBHOOK_SECRET>"}'
   ```

### Database emergency access

Connect directly to the Railway PostgreSQL instance:
```bash
railway connect PostgreSQL
```

This opens a `psql` session. Use with caution — there is no undo for `UPDATE`/`DELETE` without a transaction.
