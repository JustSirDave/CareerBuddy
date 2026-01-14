# CareerBuddy API Documentation

**Version:** 1.0  
**Last Updated:** January 14, 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Base Information](#base-information)
3. [Authentication & Security](#authentication--security)
4. [Rate Limiting](#rate-limiting)
5. [Endpoints](#endpoints)
   - [Health Checks](#health-checks)
   - [File Download](#file-download)
   - [Telegram Webhook](#telegram-webhook)
   - [Paystack Webhook](#paystack-webhook)
6. [Error Handling](#error-handling)
7. [Usage Examples](#usage-examples)
8. [Data Models](#data-models)
9. [Limitations and Guarantees](#limitations-and-guarantees)

---

## Overview

### Purpose

CareerBuddy is an AI-powered document generation service that creates professional resumes, CVs, and cover letters through a conversational Telegram bot interface. The API handles:

- **Telegram bot webhook** for user interactions
- **Payment webhook** for Paystack payment processing
- **Document generation** with AI-enhanced content
- **File delivery** for generated documents

### Intended Users

- **Telegram Bot Platform**: Receives user messages and interactions
- **Paystack Payment Gateway**: Sends payment notifications
- **Internal Services**: Health monitoring and file downloads

### Core Concepts

- **User Tiers**: Users are assigned either `free` (2 free documents) or `pro` (paid access) tier
- **Jobs**: Each document generation request creates a job that tracks conversation state
- **Document Types**: `resume`, `cv`, `cover_letter`, `revamp` (pending)
- **Templates**: Three professional templates (`template_1`, `template_2`, `template_3`)
- **Conversation State**: Multi-step conversational flow stored in job's `answers` field
- **Idempotency**: Message deduplication prevents duplicate processing

---

## Base Information

### Base URL

```
Production: https://your-domain.com
Development: http://localhost:8000
```

### Protocol

- **Transport**: HTTPS (production), HTTP (development)
- **Content Type**: `application/json`
- **Charset**: UTF-8

### Versioning

This API does not use URL-based versioning. Breaking changes will be communicated through separate deployment channels.

### Global Request Headers

All webhook requests should include:

```
Content-Type: application/json
```

### Response Format

All responses are JSON objects with the following structure:

**Success Response:**
```json
{
  "ok": true,
  "status": "ok"
}
```

**Error Response:**
```json
{
  "error": "Error category",
  "message": "Human-readable error message",
  "detail": "Additional context (optional)"
}
```

---

## Authentication & Security

### Telegram Webhook

**Authentication Method**: The Telegram webhook is secured through Telegram's built-in security:

1. **Webhook URL Registration**: Only Telegram servers know the webhook URL
2. **IP Whitelisting**: (Recommended) Restrict webhook endpoint to Telegram IP ranges
3. **HTTPS Required**: Production must use HTTPS with valid SSL certificate

**No explicit authentication header is required** for Telegram webhooks. Security relies on:
- URL secrecy
- HTTPS transport
- Request signature validation (optional but recommended)

### Paystack Webhook

**Authentication Method**: Paystack webhooks should be validated using:

1. **IP Whitelisting**: Restrict to Paystack IP ranges
2. **Signature Validation**: Verify `X-Paystack-Signature` header (recommended for production)

**Configuration Required**:
- Set `PAYSTACK_SECRET` environment variable
- Register webhook URL in Paystack dashboard

### Admin Operations

**Authentication Method**: Admin operations are authenticated using Telegram user IDs:

- **Admin Telegram IDs**: Configured via `ADMIN_TELEGRAM_IDS` environment variable (comma-separated list)
- **Authorization**: System checks if `telegram_user_id` matches admin list
- **No API keys**: Admin privileges are tied to Telegram accounts

---

## Rate Limiting

### Global Rate Limits

The API implements per-IP rate limiting:

| Window | Limit | Scope |
|--------|-------|-------|
| **1 minute** | 60 requests | Per IP address |
| **1 hour** | 1,000 requests | Per IP address |

### Rate Limit Response

When rate limit is exceeded:

**Status Code**: `429 Too Many Requests`

**Response Body**:
```json
{
  "error": "Rate limit exceeded",
  "message": "Rate limit exceeded: 60 requests per minute",
  "retry_after": "60 seconds"
}
```

### Exempted Endpoints

The following endpoints are **exempt** from rate limiting:
- `GET /health`
- `GET /health/db`
- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

### Implementation Notes

- Rate limiting uses **in-memory storage** (production should use Redis)
- Limits are enforced per source IP address
- No authentication-based rate limiting (operates at transport layer)

---

## Endpoints

### Health Checks

#### `GET /health`

Basic health check endpoint to verify API is operational.

**Request:**
```http
GET /health HTTP/1.1
Host: api.careerbuddy.com
```

**Response:**

**Status Code**: `200 OK`

```json
{
  "status": "ok",
  "env": "production"
}
```

**Fields**:
- `status` (string): Always `"ok"` if API is running
- `env` (string): Environment name (`local`, `staging`, `production`)

**Error Responses**: None (endpoint always returns 200 if API is running)

---

#### `GET /health/db`

Database connectivity health check.

**Request:**
```http
GET /health/db HTTP/1.1
Host: api.careerbuddy.com
```

**Response:**

**Status Code**: `200 OK`

```json
{
  "db": "ok"
}
```

**Error Responses**:

| Status Code | Description |
|-------------|-------------|
| `500 Internal Server Error` | Database connection failed or query timed out |

**Use Case**: Kubernetes/Docker liveness probes, monitoring systems

---

### File Download

#### `GET /download/{job_id}/{filename}`

Serves generated documents for download.

**Path Parameters**:
- `job_id` (string, required): UUID of the job that generated the document
- `filename` (string, required): Name of the file to download

**Request:**
```http
GET /download/a1b2c3d4-e5f6-7890-abcd-ef1234567890/John_Doe_Resume.docx HTTP/1.1
Host: api.careerbuddy.com
```

**Response:**

**Status Code**: `200 OK`

**Headers**:
```
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename="John_Doe_Resume.docx"
```

**Body**: Binary file content (DOCX format)

**Error Responses**:

| Status Code | Description | Response Body |
|-------------|-------------|---------------|
| `404 Not Found` | File does not exist or job ID is invalid | `{"detail": "File not found"}` |

**Notes**:
- Files are stored at `output/jobs/{job_id}/{filename}`
- No authentication required (relies on URL secrecy)
- File URLs are provided to users via Telegram after document generation
- Files persist until manually deleted (no automatic cleanup)

---

### Telegram Webhook

#### `POST /webhooks/telegram`

Receives incoming updates from Telegram Bot API.

**Request Headers**:
```
Content-Type: application/json
```

**Request Body**:

The request body follows [Telegram Update object format](https://core.telegram.org/bots/api#update). Common update types:

**Text Message**:
```json
{
  "update_id": 123456789,
  "message": {
    "message_id": 1234,
    "from": {
      "id": 987654321,
      "is_bot": false,
      "first_name": "John",
      "username": "johndoe"
    },
    "chat": {
      "id": 987654321,
      "first_name": "John",
      "username": "johndoe",
      "type": "private"
    },
    "date": 1673000000,
    "text": "/start"
  }
}
```

**Callback Query (Button Click)**:
```json
{
  "update_id": 123456790,
  "callback_query": {
    "id": "callback_id",
    "from": {
      "id": 987654321,
      "is_bot": false,
      "first_name": "John",
      "username": "johndoe"
    },
    "message": { ... },
    "data": "doc_resume"
  }
}
```

**Document Upload**:
```json
{
  "update_id": 123456791,
  "message": {
    "message_id": 1235,
    "from": { ... },
    "chat": { ... },
    "date": 1673000001,
    "document": {
      "file_name": "resume.docx",
      "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "file_id": "BQACAgQAAxk...",
      "file_size": 45678
    }
  }
}
```

**Response:**

**Status Code**: `200 OK`

```json
{
  "ok": true
}
```

**Processing Behavior**:

1. **Idempotency**: Duplicate `message_id` values are detected and ignored
2. **User Creation**: New users are automatically created on first interaction
3. **State Management**: Conversation state is persisted per user in the database
4. **Async Processing**: Bot responds via Telegram API (not in HTTP response)

**Supported Document Types**:
- `.docx` (Microsoft Word)
- `.pdf` (Adobe PDF)
- `.doc` (legacy Microsoft Word) - accepted but may have parsing issues

**Document Upload Constraints**:
- **Maximum file size**: 10 MB
- **Free tier**: Only `.docx` files accepted
- **Pro tier**: `.docx` and `.pdf` files accepted

**Error Responses**:

| Status Code | Description | Response Body |
|-------------|-------------|---------------|
| `400 Bad Request` | Invalid JSON payload | `{"detail": "Invalid JSON"}` |
| `429 Too Many Requests` | Rate limit exceeded | See [Rate Limiting](#rate-limiting) |
| `500 Internal Server Error` | Unexpected server error | `{"detail": "Internal server error"}` |

**Conversation Flow**:

The bot implements a multi-step conversational interface:

1. **Welcome** → User types `/start`
2. **Plan Selection** → User chooses Free or Premium plan
3. **Document Type** → User selects Resume, CV, or Cover Letter
4. **Template Selection** → Pro users select from 3 templates (Free users get template_1)
5. **Data Collection** → Multi-step Q&A flow:
   - Resume/CV: basics → target role → experience → education → certifications → profiles → projects → skills → personal info → summary
   - Cover Letter: basics → role/company → experience → interest → current role → achievements → skills → goals
6. **Preview** → User reviews AI-generated summary
7. **Generation** → Document is created and sent as `.docx` file
8. **PDF Conversion** → Pro users can request PDF via `/pdf` command

**Commands**:
- `/start` - Start bot or show main menu
- `/reset` - Cancel current job and start over
- `/help` - Show help message
- `/status` - Check account status and usage
- `/upgrade` - Upgrade to premium (test bypass: type "payment made")
- `/pdf` - Convert last generated DOCX to PDF (Pro only)
- `/history` - View document generation history

**Admin Commands** (restricted):
- `/admin` or `/stats` - View analytics dashboard
- `/setpro <telegram_user_id>` - Manually upgrade user to pro tier
- `/sample <type> [template]` - Generate sample document
- `/broadcast <message>` - Send message to all users

**Test Mode Payment Bypass**:

For testing without real payments, users can type:
- `payment made`
- `paid`
- `payment done`
- `payment complete`

This upgrades their account to pro tier immediately.

---

### Paystack Webhook

#### `POST /webhooks/paystack`

Receives payment notifications from Paystack payment gateway.

**Request Headers**:
```
Content-Type: application/json
X-Paystack-Signature: <signature>
```

**Request Body**:

```json
{
  "event": "charge.success",
  "data": {
    "id": 123456789,
    "domain": "live",
    "status": "success",
    "reference": "ref_123abc",
    "amount": 750000,
    "message": "Approved",
    "gateway_response": "Successful",
    "paid_at": "2023-01-15T12:00:00.000Z",
    "created_at": "2023-01-15T11:59:00.000Z",
    "channel": "card",
    "currency": "NGN",
    "metadata": {
      "user_id": "uuid-string",
      "telegram_user_id": "987654321",
      "role": "Senior Data Analyst"
    },
    "customer": {
      "id": 12345,
      "email": "user@example.com",
      "customer_code": "CUS_xxxxx"
    }
  }
}
```

**Critical Fields**:
- `event` (string): Event type (only `"charge.success"` is processed)
- `data.status` (string): Payment status (must be `"success"`)
- `data.reference` (string): Unique payment reference
- `data.amount` (integer): Amount in kobo (₦7,500 = 750000 kobo)
- `data.metadata.user_id` (string): Internal user UUID
- `data.metadata.telegram_user_id` (string): Telegram chat ID for notifications
- `data.metadata.role` (string): Target job role OR `"premium_upgrade"` for tier upgrades

**Response:**

**Status Code**: `200 OK`

```json
{
  "status": "ok"
}
```

**Processing Behavior**:

1. **Payment Recording**: All successful charges are recorded in `payments` table
2. **Premium Upgrade**: If `metadata.role == "premium_upgrade"`, user's tier is set to `"pro"`
3. **Document Unlock**: If role is specified, marks the job as paid and allows generation
4. **User Notification**: Sends confirmation message via Telegram

**Metadata Field Mapping**:

| Metadata Key | Purpose | Example |
|--------------|---------|---------|
| `user_id` | Internal user UUID | `"9e389bb3-d052-4660-a533-c4c92fb539e1"` |
| `telegram_user_id` | Telegram chat ID | `"1763950414"` |
| `role` | Job role or upgrade type | `"Senior Data Analyst"` or `"premium_upgrade"` |

**Premium Upgrade Flow**:

When `metadata.role == "premium_upgrade"`:
1. User's `tier` field is set to `"pro"`
2. User receives Telegram message:
   ```
   🎉 Payment Confirmed - You're Now Premium!
   
   ✅ Account upgraded successfully
   
   You now have access to:
   • 🎨 Multiple professional templates
   • 📄 Unlimited PDF conversions
   • 🚀 Priority AI enhancements
   • 💼 All document types
   ```

**Document Generation Flow**:

When `metadata.role` is a job role:
1. Payment is recorded for the user
2. User receives Telegram message:
   ```
   ✅ Payment confirmed!
   
   Your document generation is now unlocked.
   Return to your conversation and type 'paid' to continue.
   ```

**Error Responses**:

| Status Code | Description | Response Body |
|-------------|-------------|---------------|
| `400 Bad Request` | Invalid JSON or missing required fields | `{"detail": "Invalid payload"}` |
| `500 Internal Server Error` | Database error or notification failure | `{"status": "error", "message": "..."}` |

**Security Considerations**:

1. **Signature Validation**: Production should validate `X-Paystack-Signature` header
2. **Idempotency**: Duplicate payment references should be handled gracefully
3. **Amount Validation**: Verify amount matches expected pricing (₦7,500 = 750,000 kobo)

**Ignored Events**:

The webhook only processes `charge.success` events. Other events are logged but not acted upon:
- `charge.failed`
- `charge.pending`
- `subscription.*`
- `transfer.*`

---

## Error Handling

### Global Error Format

All API errors follow a consistent JSON structure:

```json
{
  "error": "Error category",
  "message": "Human-readable description",
  "detail": "Additional context (optional)"
}
```

### HTTP Status Codes

| Code | Meaning | When It Occurs |
|------|---------|----------------|
| `200` | Success | Request processed successfully |
| `400` | Bad Request | Invalid JSON, missing required fields, or malformed request |
| `404` | Not Found | Resource (file, endpoint) does not exist |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Unexpected server error, database failure, or external service failure |

### Telegram Webhook Error Handling

**Errors do NOT fail the HTTP request**. Instead:

1. **HTTP Response**: Always returns `200 OK` with `{"ok": true}`
2. **User Notification**: Error messages are sent to user via Telegram
3. **Logging**: Errors are logged server-side for debugging

**Example Error Messages Sent to User**:

```
❌ Sorry, there was an error processing your document. Please try again.

❌ Document appears to be empty or too short. Please upload a valid resume.

❌ File too large! Maximum: 10MB

❌ PDF uploads are a Premium feature
Free tier supports: ✅ DOCX files
Upgrade to Premium for PDF support!
```

### Paystack Webhook Error Handling

**Errors return appropriate HTTP status codes**:

- **Payment Recording Failure**: Returns `500` but payment status is still logged
- **User Not Found**: Logs warning, returns `200` (Paystack doesn't need to retry)
- **Notification Failure**: Payment is recorded, but Telegram notification may fail

**Retry Behavior**:
- Paystack retries failed webhook deliveries (non-200 responses)
- System should be idempotent to handle duplicate payments

### Client Responsibility

**Telegram Bot Platform**:
- Telegram automatically retries failed webhook deliveries
- System implements message deduplication via `message_id` tracking

**Paystack**:
- Paystack retries failed webhooks with exponential backoff
- System should validate payment references to prevent duplicate processing

### Common Error Scenarios

#### 1. Document Upload Errors

**Scenario**: User uploads invalid or empty file

**HTTP Response**: `200 OK` (no error to Telegram)

**User Notification**:
```
❌ Document Error

Document appears to be empty or too short. Please upload a valid resume.
```

#### 2. Generation Limit Reached

**Scenario**: Free user exceeds 2-document limit

**HTTP Response**: `200 OK`

**User Notification**:
```
🎯 You've reached your free tier limit (2 documents)

Each additional document costs ₦7,500.

Reply 'pay' to get your payment link, or /reset to cancel.
```

#### 3. PDF Conversion - Non-Premium User

**Scenario**: Free user tries to use `/pdf` command

**HTTP Response**: `200 OK`

**User Notification**:
```
💼 This feature requires Premium

Upgrade to Premium for:
• Unlimited PDF conversions
• 3 professional templates
• Priority support

Type 'Premium' to upgrade!
```

#### 4. Rate Limit Exceeded

**Scenario**: Too many requests from same IP

**HTTP Response**: `429 Too Many Requests`

```json
{
  "error": "Rate limit exceeded",
  "message": "Rate limit exceeded: 60 requests per minute",
  "retry_after": "60 seconds"
}
```

**Client Action**: Wait 60 seconds and retry

---

## Usage Examples

### Example 1: Complete Resume Generation Flow

This example demonstrates the full user journey from start to document delivery.

**1. User starts bot**

```http
POST /webhooks/telegram HTTP/1.1
Content-Type: application/json

{
  "update_id": 1,
  "message": {
    "message_id": 100,
    "from": {
      "id": 123456,
      "username": "john_doe"
    },
    "chat": { "id": 123456, "type": "private" },
    "text": "/start"
  }
}
```

**Response**: `200 OK`

**Bot Action**: Sends welcome message via Telegram with buttons [Free Plan] [Premium Plan]

---

**2. User selects Free Plan**

```http
POST /webhooks/telegram HTTP/1.1

{
  "update_id": 2,
  "callback_query": {
    "id": "cb1",
    "from": { "id": 123456 },
    "data": "plan_free"
  }
}
```

**Bot Action**: Confirms free plan, shows document menu [Resume] [CV] [Cover Letter]

---

**3. User selects Resume**

```http
POST /webhooks/telegram HTTP/1.1

{
  "update_id": 3,
  "callback_query": {
    "id": "cb2",
    "data": "doc_resume"
  }
}
```

**Bot Action**: Asks for basic information (name, email, phone, location)

---

**4. User provides basic info**

```http
POST /webhooks/telegram HTTP/1.1

{
  "update_id": 4,
  "message": {
    "message_id": 101,
    "text": "John Doe, john@email.com, +234801234567, Lagos, Nigeria"
  }
}
```

**Bot Action**: Asks for target role

---

**5. Conversation continues...**

(User provides: target role, experience, education, skills, etc.)

---

**6. Preview and Confirmation**

```http
POST /webhooks/telegram HTTP/1.1

{
  "update_id": 15,
  "message": {
    "text": "yes"
  }
}
```

**Bot Action**: Generates document, sends `.docx` file via Telegram

---

**7. User downloads document**

```http
GET /download/a1b2c3d4-e5f6-7890-abcd-ef1234567890/John_Doe_Resume.docx HTTP/1.1
```

**Response**: Binary DOCX file

---

### Example 2: Premium Upgrade Flow

**1. User requests upgrade**

```http
POST /webhooks/telegram HTTP/1.1

{
  "message": {
    "text": "/upgrade"
  }
}
```

**Bot Action**: Shows upgrade information and price (₦7,500)

---

**2. User confirms (test mode)**

```http
POST /webhooks/telegram HTTP/1.1

{
  "message": {
    "text": "payment made"
  }
}
```

**Bot Action**: Upgrades user to `pro` tier, confirms upgrade

---

**3. (Production) Paystack payment webhook**

```http
POST /webhooks/paystack HTTP/1.1
X-Paystack-Signature: signature_here

{
  "event": "charge.success",
  "data": {
    "status": "success",
    "reference": "ref_abc123",
    "amount": 750000,
    "metadata": {
      "user_id": "user-uuid",
      "telegram_user_id": "123456",
      "role": "premium_upgrade"
    }
  }
}
```

**Response**: `200 OK`

**Bot Action**: Upgrades user, sends confirmation message

---

### Example 3: PDF Conversion (Pro User)

**1. User requests PDF**

```http
POST /webhooks/telegram HTTP/1.1

{
  "message": {
    "text": "/pdf"
  }
}
```

**Bot Action**: Converts last generated DOCX to PDF, sends PDF file

---

### Example 4: Document Upload for Revamp (Currently Disabled)

**1. User uploads document**

```http
POST /webhooks/telegram HTTP/1.1

{
  "message": {
    "document": {
      "file_name": "old_resume.docx",
      "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "file_id": "BQACAgQAAxk...",
      "file_size": 50000
    }
  }
}
```

**Bot Action**: Shows "Coming Soon" message (feature is pending)

---

### Example 5: Admin Operations

**1. Admin checks stats**

```http
POST /webhooks/telegram HTTP/1.1

{
  "message": {
    "from": { "id": 999999 },  // Admin ID
    "text": "/stats"
  }
}
```

**Bot Action**: Shows analytics dashboard with user metrics, document counts, revenue

---

**2. Admin upgrades user**

```http
POST /webhooks/telegram HTTP/1.1

{
  "message": {
    "text": "/setpro 123456"
  }
}
```

**Bot Action**: Upgrades user 123456 to pro tier, notifies them

---

## Data Models

### User Model

```typescript
{
  id: string;                    // UUID
  telegram_user_id: string;      // Telegram chat ID (unique)
  telegram_username: string;     // Telegram @username (optional)
  name: string;                  // User's full name (optional)
  email: string;                 // Email address (optional)
  phone: string;                 // Phone number (optional)
  locale: string;                // Language code (default: "en")
  tier: "free" | "pro";          // User tier
  generation_count: string;      // JSON: {"role": count, ...}
  created_at: DateTime;          // Account creation timestamp
  updated_at: DateTime;          // Last update timestamp
}
```

**Generation Count Format**:
```json
{
  "Senior Data Analyst": 2,
  "Software Engineer": 1,
  "Project Manager": 1
}
```

---

### Job Model

```typescript
{
  id: string;                    // UUID
  user_id: string;               // Foreign key to User
  type: "resume" | "cv" | "cover_letter" | "revamp";
  status: string;                // Current job status
  answers: object;               // Conversation state + user data
  draft_text: string;            // Generated draft (file path)
  final_text: string;            // Final version (file path)
  last_msg_id: string;           // Last processed message ID (deduplication)
  created_at: DateTime;
  updated_at: DateTime;
}
```

**Status Flow**:
```
collecting → draft_ready → preview_ready → awaiting_payment → paid → rendering → delivered → closed
```

**Answers Object Structure (Resume)**:
```json
{
  "_step": "preview",
  "template": "template_1",
  "basics": {
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+234801234567",
    "location": "Lagos, Nigeria",
    "title": "Senior Data Analyst"
  },
  "target_role": "Senior Data Analyst",
  "experiences": [
    {
      "role": "Data Analyst",
      "company": "Tech Corp",
      "city": "Lagos",
      "start": "Jan 2020",
      "end": "Present",
      "bullets": [
        "Increased revenue by 40%",
        "Built 15+ dashboards"
      ]
    }
  ],
  "education": [
    {
      "degree": "B.Sc. Computer Science",
      "school": "University of Lagos",
      "year": "2019"
    }
  ],
  "skills": ["Python", "SQL", "Tableau", "Excel"],
  "certifications": [
    {"details": "AWS Certified Solutions Architect"}
  ],
  "profiles": [
    {"platform": "LinkedIn", "url": "https://linkedin.com/in/johndoe"}
  ],
  "projects": [
    {"details": "Built sales forecasting model with 95% accuracy"}
  ],
  "summary": "Experienced Data Analyst with 5+ years...",
  "personal_traits": "Detail-oriented, strong communicator"
}
```

---

### Payment Model

```typescript
{
  id: string;                    // UUID
  user_id: string;               // Foreign key to User
  job_id: string;                // Foreign key to Job (optional)
  provider: "paystack";          // Payment provider
  amount: number;                // Amount in kobo
  reference: string;             // Unique payment reference
  status: "success" | "pending" | "failed";
  metadata: object;              // Additional payment data
  raw_payload: object;           // Full webhook payload
  created_at: DateTime;
}
```

---

## Limitations and Guarantees

### Rate Limits

- **60 requests per minute** per IP address
- **1,000 requests per hour** per IP address
- Rate limiting is **IP-based only** (no user-based limits)

### Performance

- **Response Time**: 95th percentile < 2 seconds for text messages
- **Document Generation**: 10-30 seconds depending on complexity
- **PDF Conversion**: 5-15 seconds additional processing time

### File Storage

- **No automatic cleanup**: Generated files persist indefinitely
- **Maximum upload size**: 10 MB per file
- **Supported formats**: `.docx`, `.pdf` (pro only)
- **Storage location**: Local filesystem at `output/jobs/{job_id}/`

### Generation Limits

| Tier | Limit | Cost per Additional Document |
|------|-------|------------------------------|
| Free | 2 documents total | ₦7,500 per document |
| Pro | Unlimited | ₦7,500 per document |

### Document Types

| Type | Free Tier | Pro Tier | Status |
|------|-----------|----------|--------|
| Resume | ✅ Available | ✅ Available | Active |
| CV | ✅ Available | ✅ Available | Active |
| Cover Letter | ❌ Premium Only | ✅ Available | Active |
| Revamp | 🔜 Coming Soon | 🔜 Coming Soon | Pending |

### Templates

| Template | Free Tier | Pro Tier | Style |
|----------|-----------|----------|-------|
| Template 1 | ✅ Default | ✅ Available | Classic Professional |
| Template 2 | ❌ | ✅ Available | Modern Minimal |
| Template 3 | ❌ | ✅ Available | Executive Bold |

### Guarantees

#### What the API Guarantees

✅ **Idempotency**: Duplicate messages (same `message_id`) are processed exactly once  
✅ **Data Persistence**: User data and conversation state are persisted in PostgreSQL  
✅ **Eventual Consistency**: Webhook processing is asynchronous; bot responses may be delayed  
✅ **Backward Compatibility**: Existing webhook contracts will not break without notice  

#### What the API Does NOT Guarantee

❌ **Message Ordering**: Messages may arrive out of order; system relies on `message_id` for deduplication  
❌ **Real-Time Delivery**: Bot responses are asynchronous and may be delayed during high load  
❌ **File Retention**: Files are not automatically deleted; manual cleanup required  
❌ **Payment Validation**: Amount validation in webhooks is advisory; production should validate signatures  
❌ **AI Quality**: AI-generated content quality varies; no guarantees on output quality  
❌ **Uptime SLA**: No formal uptime guarantee (production readiness in progress)  

### Known Limitations

1. **Rate Limiter**: Uses in-memory storage; resets on pod restart (production should use Redis)
2. **Admin Authentication**: Based on Telegram IDs only; no API key-based authentication
3. **Payment Gateway**: Test mode bypasses payment; production integration incomplete
4. **Error Recovery**: Limited automatic retry logic; users must manually retry failed operations
5. **Scalability**: Single-instance deployment; horizontal scaling requires Redis for rate limiting and session state

### Deprecation Policy

- **Breaking Changes**: 30-day advance notice via email and documentation updates
- **New Features**: Announced via `/broadcast` command to all users
- **Endpoint Retirement**: 90-day deprecation period before removal

---

## Additional Resources

### Environment Variables

Required environment variables for deployment:

```bash
# Application
APP_ENV=production
APP_PORT=8000
PUBLIC_URL=https://api.careerbuddy.com

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_TELEGRAM_IDS=123456,789012  # Comma-separated

# Database
DATABASE_URL=postgresql://user:pass@host:5432/buddy

# Redis
REDIS_URL=redis://host:6379/0

# AI/LLM
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

# Payments
PAYSTACK_SECRET=your_secret_here

# Storage (Optional)
S3_ENDPOINT=https://s3.amazonaws.com
S3_REGION=us-east-1
S3_BUCKET=careerbuddy-files
S3_ACCESS_KEY_ID=your_key
S3_SECRET_ACCESS_KEY=your_secret
```

### Monitoring Endpoints

- **Health Check**: `GET /health` - Basic liveness probe
- **Database Health**: `GET /health/db` - Database connectivity check
- **Request ID Header**: All responses include `X-Request-ID` for tracing

### Support

For API issues, contact:
- **Telegram Support**: Type `/help` in the bot
- **Admin Contact**: Message support account at support number (configured per deployment)

---

**End of Documentation**

*This documentation describes the API as implemented. For feature requests or bug reports, please contact the development team.*
