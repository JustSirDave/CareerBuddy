# CareerBuddy - Testing Guide

**Date:** January 2026  
**Purpose:** Comprehensive testing checklist for all implemented features

---

## 🔧 **Setup Requirements**

Before testing, ensure:

1. **Docker services are running:**
   ```bash
   docker-compose up -d
   ```

2. **Database migrations applied:**
   ```bash
   docker-compose exec api alembic upgrade head
   ```

3. **Environment variables set:**
   - `TELEGRAM_BOT_TOKEN` - Your bot token
   - `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` - For AI features
   - `ADMIN_TELEGRAM_IDS` - Your Telegram user ID for admin testing
   - `PAYSTACK_SECRET` - (Optional, using test bypass)

4. **Get your Telegram User ID:**
   - Message `@userinfobot` on Telegram
   - Save your ID for admin configuration

---

## 📋 **Testing Checklist**

### **Phase 1: Basic User Flow (Free Tier)**

#### ✅ Test 1: Initial Setup & Registration
- [ ] Send `/start` to the bot
- [ ] Bot shows welcome message with menu
- [ ] Select "Free" plan
- [ ] Verify user is created in database

**Expected Result:** Welcome message, document type menu shown

---

#### ✅ Test 2: Resume Generation Flow (Template 1)
- [ ] Select "Resume" from menu
- [ ] Follow the conversational flow:
  - [ ] **Target Role:** "Senior Data Analyst"
  - [ ] **Basic Info:** "John Doe, Data Analyst, john@example.com, +1234567890, Lagos Nigeria"
  - [ ] **AI Skills:** Bot generates 5-8 skills, select 5 by number (e.g., "1, 2, 3, 4, 5")
  - [ ] **Experience:** "Data Analyst, TechCorp, Lagos, Jan 2020, Present"
  - [ ] **Bullets:** Add 2-3 achievement bullets, type "done"
  - [ ] **Education:** "University of Lagos, 2016-2020"
  - [ ] **Certifications:** "AWS Certified, Amazon, 2021" or "skip"
  - [ ] **Projects:** Describe 1-2 projects or "skip"
  - [ ] **Profiles:** "LinkedIn, https://linkedin.com/in/johndoe" or "skip"
  - [ ] **Personal Info:** Share brief background
  - [ ] **Summary:** AI generates professional summary

**Expected Result:** 
- DOCX document sent to Telegram
- All sections properly formatted
- No extra spacing issues

---

#### ✅ Test 3: Template Selection
- [ ] Start new resume with `/reset`
- [ ] When asked for template, select "2" (Modern Minimal)
- [ ] Complete the flow
- [ ] Verify template 2 styling (centered header, blue accents)

**Expected Result:** Different visual style than template 1

---

#### ✅ Test 4: Free Tier Limits
- [ ] Generate 2 documents (exhausts free tier)
- [ ] Try to generate 3rd document
- [ ] Should see payment prompt

**Expected Result:** Payment required message after 2 documents

---

### **Phase 2: Premium Upgrade (Test Mode)**

#### ✅ Test 5: Upgrade to Premium
- [ ] Type `/upgrade`
- [ ] Bot shows premium benefits and test instruction
- [ ] Type `payment made`
- [ ] Verify upgrade confirmation message

**Expected Result:**
```
🎉 Payment Confirmed - You're Now Premium!
✅ Account upgraded successfully
...
```

**Verify in DB:** User's `tier` column should be "pro"

---

#### ✅ Test 6: Check Premium Status
- [ ] Type `/status`
- [ ] Should show "Premium" plan
- [ ] Shows generation count

**Expected Result:** Status shows premium tier

---

#### ✅ Test 7: Already Premium Check
- [ ] Type `/upgrade` again
- [ ] Should inform already premium

**Expected Result:** "You're Already Premium!" message

---

### **Phase 3: PDF Conversion (Premium Only)**

#### ✅ Test 8: PDF Export - Template 1
- [ ] Generate a resume with Template 1 (as premium user)
- [ ] Type `/pdf`
- [ ] Bot generates and sends PDF

**Verify:**
- [ ] PDF layout matches DOCX exactly
- [ ] No extra spacing issues
- [ ] Header, experience, education, skills all present
- [ ] Job title visible in header
- [ ] Contact line formatted correctly (Location | Phone | Email)
- [ ] Horizontal line thickness looks good
- [ ] Currency symbols (₦) display as "N"
- [ ] Bullet points properly indented

**Expected Result:** Pixel-perfect PDF matching DOCX layout

---

#### ✅ Test 9: PDF Export - Template 2
- [ ] Generate resume with Template 2
- [ ] Type `/pdf`
- [ ] Verify PDF has modern minimal styling

**Verify:**
- [ ] Centered header
- [ ] Dark blue section headings
- [ ] Clean, contemporary design

---

#### ✅ Test 10: PDF Export - Template 3
- [ ] Generate resume with Template 3
- [ ] Type `/pdf`
- [ ] Verify PDF has executive bold styling

**Verify:**
- [ ] Left-aligned header
- [ ] Bold black section headings
- [ ] Larger margins (0.75")
- [ ] Authoritative presence

---

#### ✅ Test 11: PDF Without Premium
- [ ] Create a new free tier user
- [ ] Generate a document
- [ ] Try `/pdf` command
- [ ] Should be blocked

**Expected Result:**
```
🔒 PDF Export is a Premium Feature
...
Type /upgrade to get premium access now!
```

---

#### ✅ Test 12: Edited Document Upload & Conversion
- [ ] Generate a document
- [ ] Download the .docx file
- [ ] Edit it (add/remove content)
- [ ] Upload edited .docx back to bot
- [ ] Type `/pdf`
- [ ] Bot converts the edited version

**Expected Result:** PDF of the edited document (may have spacing issues if complex edits)

---

### **Phase 4: AI Features**

#### ✅ Test 13: AI Skill Generation
- [ ] Start resume flow
- [ ] Provide target role: "Full Stack Developer"
- [ ] AI should generate 5-8 relevant skills

**Verify:**
- [ ] Skills are relevant to role
- [ ] Skills are properly numbered
- [ ] Can select by numbers (e.g., "1, 3, 5, 7, 8")

---

#### ✅ Test 14: AI Summary Generation
- [ ] Complete resume flow with personal info
- [ ] AI generates professional summary

**Verify:**
- [ ] Summary is coherent and professional
- [ ] Reflects the role and experience provided
- [ ] Not too generic

---

#### ✅ Test 15: Error Handling - Invalid Skill Selection
- [ ] During skill selection, type invalid input: "python, sql"
- [ ] Bot should guide user to use numbers

**Expected Result:** Helpful error message with example

---

#### ✅ Test 16: Error Handling - Invalid Education Format
- [ ] During education, type: "just a university name"
- [ ] Bot should ask for correct format

**Expected Result:** Format guidance with example

---

### **Phase 5: Admin Commands**

#### ✅ Test 17: Admin Access Check
- [ ] Set your Telegram ID in `ADMIN_TELEGRAM_IDS` env var
- [ ] Restart the API container
- [ ] Type `/admin` or `/stats`
- [ ] Should see admin dashboard

**Expected Result:**
```
📊 Career Buddy - Admin Stats
...
```

---

#### ✅ Test 18: Non-Admin Blocked
- [ ] Use a different Telegram account (not in admin list)
- [ ] Try `/admin`, `/stats`, `/broadcast`, `/setpro`
- [ ] Should be blocked

**Expected Result:**
```
⚠️ This command is only available to administrators.
```

---

#### ✅ Test 19: Manual User Upgrade
- [ ] As admin, type: `/setpro <target_user_telegram_id>`
- [ ] Should upgrade the target user
- [ ] Target user receives notification

**Expected Result:**
- Admin sees success confirmation
- Target user gets premium notification
- Target user's tier updated to "pro" in DB

---

#### ✅ Test 20: Broadcast Message
- [ ] As admin, type: `/broadcast Hello everyone! Testing broadcast.`
- [ ] All users receive the message

**Expected Result:**
```
📢 Announcement from Career Buddy

Hello everyone! Testing broadcast.
```

---

#### ✅ Test 21: Sample Document Generation
- [ ] As admin, type: `/sample resume`
- [ ] Bot generates sample resume instantly
- [ ] Try: `/sample resume 2` for template 2
- [ ] Try: `/sample cv 3` for CV with template 3

**Expected Result:** Instant document generation without flow

---

### **Phase 6: Edge Cases & Error Handling**

#### ✅ Test 22: Reset Mid-Flow
- [ ] Start resume generation
- [ ] Mid-way through, type `/reset`
- [ ] Job should be cancelled
- [ ] Can start fresh

**Expected Result:** Clean reset, no data retained

---

#### ✅ Test 23: Long Content Handling
- [ ] Create resume with very long experience bullets (200+ characters each)
- [ ] Add 5+ work experiences
- [ ] Generate document and PDF

**Expected Result:** Content properly paginated, no cutoff

---

#### ✅ Test 24: Special Characters in Content
- [ ] Use special characters: @, #, $, %, ₦, &, *
- [ ] Use accented characters: é, ñ, ü
- [ ] Generate document and PDF

**Expected Result:** Characters display correctly (₦ becomes N in PDF)

---

#### ✅ Test 25: Empty/Minimal Data
- [ ] Create resume with minimal info (name, email, 1 skill)
- [ ] Skip most optional fields
- [ ] Generate document

**Expected Result:** Document generates without errors, sections present but sparse

---

#### ✅ Test 26: Multiple Concurrent Users
- [ ] Have 2+ Telegram accounts interact with bot simultaneously
- [ ] Each follows different flows
- [ ] Verify no data mixing between users

**Expected Result:** Each user's data isolated correctly

---

#### ✅ Test 27: Message Deduplication
- [ ] Send same message twice quickly
- [ ] Bot should process only once

**Expected Result:** No duplicate responses or processing

---

### **Phase 7: Cover Letter & Revamp**

#### ✅ Test 28: Cover Letter Generation (Premium)
- [ ] As premium user, select "Cover Letter"
- [ ] Follow the flow
- [ ] Verify document generation

**Expected Result:** Professional cover letter generated

---

#### ✅ Test 29: Cover Letter Blocked (Free)
- [ ] As free user, try to select "Cover Letter"
- [ ] Should be blocked

**Expected Result:** Premium feature prompt

---

#### ✅ Test 30: Document Revamp
- [ ] Select "Revamp"
- [ ] Paste existing resume content
- [ ] AI improves content
- [ ] Generate improved document

**Expected Result:** Enhanced version of original content

---

## 🐛 **Known Issues & Limitations**

1. **User-Edited DOCX → PDF:** May have spacing issues (LibreOffice conversion)
2. **Currency Symbol:** ₦ displays as "N" in PDFs (font limitation)
3. **Maximum 5 Documents per Role:** By design
4. **Free Tier:** Limited to 2 documents

---

## 🔍 **Database Verification Queries**

```sql
-- Check user tier
SELECT telegram_user_id, tier, generation_count FROM users;

-- Check payments
SELECT user_id, reference, amount, status FROM payments ORDER BY created_at DESC;

-- Check completed jobs
SELECT user_id, type, status FROM jobs WHERE status = 'completed';

-- Check premium users
SELECT COUNT(*) FROM users WHERE tier = 'pro';
```

---

## 📊 **Success Criteria**

### ✅ **Minimum Passing:**
- All Phase 1 tests pass (basic flow)
- PDF generation works for all 3 templates
- Premium upgrade bypass works
- Admin commands properly gated

### ✅ **Full Success:**
- All 30 tests pass
- No critical errors in logs
- PDFs match DOCX layouts
- AI features generate quality content
- Payment bypass works reliably

---

## 🚀 **Next Steps After Testing**

1. **If tests pass:**
   - Commit and push to GitHub
   - Deploy to production environment
   - Integrate real Paystack payment gateway
   - Remove payment bypass code

2. **If issues found:**
   - Document specific failures
   - Check logs for errors
   - Debug and fix
   - Re-test

---

## 📝 **Testing Notes Template**

Use this to track your testing:

```
Date: _______________
Tester: _______________
Environment: Development / Staging / Production

| Test # | Test Name | Status | Notes |
|--------|-----------|--------|-------|
| 1 | Initial Setup | ✅/❌ | |
| 2 | Resume Gen | ✅/❌ | |
| ... | ... | ... | |

Overall Result: PASS / FAIL
Critical Issues: [List any]
```

---

**Good luck with testing! 🎉**
