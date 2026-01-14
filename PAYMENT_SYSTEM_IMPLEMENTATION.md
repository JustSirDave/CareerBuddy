# Payment Gateway System Implementation
**Author: Sir Dave**  
**Date: 2026-01-14**

## Overview
Complete redesign of the payment and quota system from role-based tracking to document-type-based tracking with monthly quotas and premium packages.

---

## 🎯 New System Design

### **Free Tier** (Monthly Reset)
- **1 Resume** per month
- **1 CV** per month
- **1 Revamp** per month
- **DOCX only** (no PDF)
- **❌ No Cover Letters**
- ✅ Resets monthly

### **Premium Tier** (₦7,500/month)
- **2 Resumes** per month
- **2 CVs** per month
- **1 Cover Letter** per month
- **1 Revamp** per month
- **PDF + DOCX** format
- ✅ Resets monthly
- Auto-renews every 30 days

### **Coming Soon**
- Pay-per-document feature

---

## 📊 Key Changes

### 1. **Database Schema** (`User` model)
Added two new columns:
- `quota_reset_at` - Timestamp for monthly quota reset
- `premium_expires_at` - Timestamp for premium subscription expiry

Updated:
- `generation_count` - Now tracks document types instead of roles
  - **Old:** `{"Data Analyst": 2, "Software Engineer": 1}`
  - **New:** `{"resume": 1, "cv": 1, "cover_letter": 0, "revamp": 0}`

### 2. **Payment Service** (`payments.py`)
Complete rewrite with new functions:

#### Quota Management
- `get_document_counts(user)` - Get current document usage
- `check_and_reset_quota(db, user)` - Check and apply monthly reset
- `check_premium_expiry(db, user)` - Check and downgrade expired premium
- `can_generate_document(user, doc_type)` - Check if user can create document
- `can_use_pdf(user)` - Check if user has PDF permission
- `update_document_count(db, user, doc_type)` - Track document creation
- `get_quota_status(user)` - Get comprehensive quota information

#### Premium Management
- `upgrade_to_premium(db, user)` - Upgrade user to premium tier
- `create_premium_payment_link(user)` - Create Paystack payment link

#### Constants
```python
QUOTA_LIMITS = {
    "free": {
        "resume": 1,
        "cv": 1,
        "cover_letter": 0,
        "revamp": 1,
        "pdf_allowed": False,
    },
    "pro": {
        "resume": 2,
        "cv": 2,
        "cover_letter": 1,
        "revamp": 1,
        "pdf_allowed": True,
    }
}
PREMIUM_PACKAGE_PRICE = 7500  # ₦7,500/month
```

### 3. **Router Updates** (`router.py`)
- Added quota/premium expiry checks at the start of each flow handler
- Updated all `can_generate()` calls to `can_generate_document(user, doc_type)`
- Updated all `update_generation_count()` calls to `update_document_count(user, doc_type)`
- Added PDF format restriction checks
- Updated `/status` command to show detailed quota breakdown
- Updated `/upgrade` command to show new premium package details
- Updated payment bypass logic to use `upgrade_to_premium()`

---

## 🔄 Migration Process

### Step 1: Apply SQL Migration
```bash
docker exec -i careerbuddy-db psql -U postgres -d buddy < backend/migrations/001_add_premium_tracking.sql
```

### Step 2: Restart Services
```bash
docker-compose restart api
```

### Step 3: Verify Migration
```sql
-- Check schema
\d users

-- Check updated generation_count format
SELECT telegram_user_id, generation_count, quota_reset_at, premium_expires_at, tier 
FROM users 
LIMIT 5;
```

---

## 🧪 Testing the New System

### Test Payment Bypass
```
User: payment made
Bot: 🎉 Welcome to Premium!
     Package: 2 Resume + 2 CV + 1 Cover Letter + 1 Revamp
     Price: ₦7,500/month
```

### Test Quota Status
```
User: /status
Bot: 📊 Your Account Status
     Plan: Premium ⭐
     
     📦 Monthly Quota:
     Resume: 0/2 used (2 remaining)
     CV: 0/2 used (2 remaining)
     Cover Letter: 0/1 used (1 remaining)
     Revamp: 0/1 used (1 remaining)
     
     PDF Format: ✅ Enabled
```

### Test Quota Limits
```
# Free user creates 2nd resume
Bot: 📊 RESUME Quota Reached
     You've used all 1 resume in your free plan.
     
     💡 Upgrade to Premium for:
     • More documents (2 Resume + 2 CV)
     • 1 Cover Letter
     • PDF format
     
     Type /upgrade to get Premium for just ₦7,500/month!
```

### Test PDF Restriction
```
# Free user: /pdf
Bot: 🔒 PDF Format is a Premium Feature
     
     Upgrade to Premium to unlock:
     • Unlimited PDF conversions
     • 2 Resume + 2 CV per month
     • 1 Cover Letter
     
     Type /upgrade for just ₦7,500/month!
```

---

## 🔧 Automated Processes

### Monthly Quota Reset
The `check_and_reset_quota(db, user)` function is called at the start of every document generation flow. It:
1. Checks if 30 days have passed since last reset
2. Resets all document counts to 0
3. Sets next reset date to +30 days
4. Commits changes

### Premium Expiry Check
The `check_premium_expiry(db, user)` function is called at the start of every document generation flow. It:
1. Checks if premium has expired
2. Downgrades user to "free" tier
3. User retains any remaining documents from free quota
4. Logs the downgrade

---

## 📝 Code Examples

### Checking Quota
```python
can_gen, reason = payments.can_generate_document(user, "resume")

if not can_gen:
    if reason.startswith("quota_exceeded"):
        _, doc_name, limit = reason.split("|")
        return f"You've used all {limit} {doc_name}(s) this month"
```

### Upgrading to Premium
```python
success = payments.upgrade_to_premium(db, user)
if success:
    # User is now pro, quota reset, premium_expires_at set to +30 days
    pass
```

### Getting Quota Status
```python
status = payments.get_quota_status(user)
# Returns:
# {
#   "tier": "pro",
#   "resume": {"used": 1, "limit": 2, "remaining": 1},
#   "cv": {"used": 0, "limit": 2, "remaining": 2},
#   "cover_letter": {"used": 1, "limit": 1, "remaining": 0},
#   "revamp": {"used": 0, "limit": 1, "remaining": 1},
#   "pdf_allowed": True,
#   "quota_resets_at": "2026-02-14T12:00:00Z",
#   "premium_expires_at": "2026-02-14T12:00:00Z"
# }
```

---

## 🚨 Important Notes

1. **Monthly Reset is Automatic** - No cron job needed; runs on first request after 30 days
2. **Premium Expiry is Automatic** - User auto-downgrades to free tier when premium expires
3. **Quota Tracking is Document-Based** - Each document type has its own quota
4. **PDF Permission is Tier-Based** - Free users cannot access PDF conversion
5. **Payment Bypass Works** - Type "payment made" to test premium upgrade
6. **Old Data is Migrated** - Existing users get fresh quota in new format

---

## 🔗 Related Files
- `backend/app/models/user.py` - User model with new fields
- `backend/app/services/payments.py` - Complete payment/quota system
- `backend/app/services/router.py` - Integration with flows
- `backend/migrations/001_add_premium_tracking.sql` - Database migration
- `backend/migrations/add_premium_tracking.py` - Alembic migration (if used)

---

## ✅ Verification Checklist
- [ ] Database migration applied successfully
- [ ] Services restarted
- [ ] `/status` shows new quota format
- [ ] `/upgrade` shows premium package details
- [ ] "payment made" bypass works
- [ ] Free tier quota limits enforced
- [ ] Premium tier quota limits enforced
- [ ] PDF restriction works for free users
- [ ] Monthly quota reset works (test with manual date change)
- [ ] Premium expiry works (test with manual date change)
- [ ] Document generation tracked correctly
- [ ] All document types (resume, cv, cover_letter, revamp) work

---

**Implementation Complete!** 🎉
The payment gateway system is now fully redesigned and ready for testing.
