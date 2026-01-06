# 📧 Email Classification System v3.0

## Overview

Aivis uses a **single, unified email classification system** with 10 categories to help users manage their inbox efficiently.

## 10 Email Categories

### High Priority (Facts Extracted)
These categories are important and facts are automatically extracted:

1. **`urgent`** - Requires immediate attention
   - Keywords: deadline, urgent, asap, critical, emergency
   - Sender patterns: boss, leadership

2. **`action_items`** - Tasks requiring action
   - Keywords: todo, action, task, complete, respond
   - Questions, requests, forms

3. **`clients`** - Client communications
   - External domain communications
   - Business-related conversations

4. **`waiting_for_reply`** - Awaiting response
   - Follow-ups, reminders, "any update?" messages

5. **`normal`** - General business emails
   - Standard work communications

### Low Priority (No Facts Extracted)
These categories are filtered and no facts are stored:

6. **`notifications`** - Automated system alerts
   - Build notifications, CI/CD, monitoring alerts
   - GitHub, Slack, Jira notifications

7. **`newsletters`** - Marketing emails and updates
   - Promotional content, industry news
   - Weekly digests

8. **`promotional`** - Sales and promotions
   - Discounts, offers, sales

9. **`transactional`** - Receipts and confirmations
   - Order confirmations, shipping updates
   - Password resets, account notifications

10. **`social`** - Social media notifications
    - LinkedIn, Twitter, Facebook updates

---

## How Classification Works

### On First Login
When a user connects their Google account:

1. **OAuth callback triggers background classification**
   - Server calls `/api/gmail/classify-background`
   - Processes up to 200 recent emails
   - Non-blocking - user can start using the app immediately

2. **Classification + Fact Extraction**
   - Each email is classified into one of 10 categories
   - If category is "high priority" → facts are extracted
   - If category is "low priority" → facts are skipped

3. **Status tracking**
   - `users.initial_email_classification_done` → false (in progress)
   - When complete → true
   - Check status: `GET /memory/email-processing-status?user_id=<id>`

### On New Emails
When new emails arrive:

1. **Real-time classification** in `classify_single_email()`
2. **Background fact extraction** for high-priority categories
3. **Instant inbox triage** with categorized results

---

## Gmail Page

The Gmail inbox page shows emails grouped by all 10 categories:

```
📧 Inbox Categories:
├── Urgent (2)
├── Action Items (5)
├── Waiting for Reply (3)
├── Clients (8)
├── Invoices (1)
├── Normal (12)
├── Notifications (15)
├── Newsletters (7)
├── Promotional (4)
├── Transactional (2)
└── Social (3)
```

**Filter by category:**
```bash
GET /api/gmail/triaged-inbox?user_id=v&category_filter=urgent
```

---

## API Endpoints

### Classify Background (On First Login)
```bash
POST /api/gmail/classify-background
{
  "user_id": "v",
  "max_emails": 200
}
```

**Response:**
```json
{
  "success": true,
  "message": "Background classification started",
  "user_id": "v"
}
```

### Check Classification Status
```bash
GET /memory/email-processing-status?user_id=v
```

**Response:**
```json
{
  "success": true,
  "user_id": "v",
  "email_count": 150,
  "classified_count": 120,
  "status": "in_progress",
  "classification_version": "3.0",
  "started_at": "2026-01-06T...",
  "message": "Classifying emails... (120/150 done)"
}
```

### Get Triaged Inbox
```bash
GET /api/gmail/triaged-inbox?user_id=v&category_filter=urgent
```

**Response:**
```json
{
  "success": true,
  "categories": {
    "urgent": [...],
    "action_items": [...],
    "clients": [...],
    ...
  },
  "total": 47
}
```

---

## Classification Algorithm

The classifier uses a **hybrid approach**:

1. **Rule-based scoring** (fast, keyword-based)
   - Subject/body keywords
   - Sender patterns
   - Email structure

2. **LLM-based classification** (accurate, context-aware)
   - Used when rule scores are inconclusive
   - Provides confidence scores

3. **Priority ordering**
   - Filters out low-priority categories first
   - Then ranks high-priority categories
   - Falls back to `normal` if uncertain

See `app/tools/email/classifier.py` for implementation details.

---

## Fact Extraction Filter

**Only high-priority emails get fact extraction:**

```python
IMPORTANT_CATEGORIES = [
    'urgent',
    'action_items',
    'clients',
    'waiting_for_reply',
    'normal'
]

if email_category in IMPORTANT_CATEGORIES:
    extract_facts_from_email(user_id, email_data)
```

This saves API costs and improves fact quality by focusing on actionable content.

---

## Code Locations

- **Classification logic:** `app/tools/email/classifier.py`
- **Gmail service:** `app/services/gmail_service.py`
  - `classify_single_email()` - classify one email
  - `classify_background()` - batch classify on login
  - `triaged_inbox()` - get categorized inbox
  - `extract_facts_from_email()` - extract facts (filtered)
- **OAuth callback:** `server.py` → `google_callback()`
- **API routes:** `app/api/memory_routes.py`

---

## Testing

### Test Classification
```bash
# Start server
python server.py

# Trigger background classification
curl -X POST http://localhost:10000/api/gmail/classify-background \
  -H "Content-Type: application/json" \
  -d '{"user_id": "v", "max_emails": 50}'

# Check status
curl "http://localhost:10000/memory/email-processing-status?user_id=v"

# View triaged inbox
curl "http://localhost:10000/api/gmail/triaged-inbox?user_id=v"
```

---

## Migration from Old System

If you had the old classification system (v1.0 or v2.0):

1. **No migration needed** - emails will be re-classified automatically on first use
2. **Classification version** tracked in `emails.classification_version`
3. **Old categories are overwritten** with new v3.0 categories

---

## Environment Variables

```bash
# .env
OPENAI_API_KEY=sk-...           # For LLM-based classification
GOOGLE_CLIENT_ID=...            # For Gmail OAuth
GOOGLE_CLIENT_SECRET=...        # For Gmail OAuth
```

---

## Performance

- **Background processing:** Non-blocking, uses threading
- **Caching:** Stores classifications in MongoDB
- **API costs:** ~$0.001 per email (LLM only when needed)
- **Speed:** ~200 emails classified in 2-3 minutes

---

## Troubleshooting

### Classification not working
```bash
# Check server logs
tail -f logs/server.log

# Verify database connection
curl http://localhost:10000/memory/health

# Check classification status
curl "http://localhost:10000/memory/email-processing-status?user_id=<id>"
```

### Categories not showing in Gmail page
- Ensure `triaged_inbox()` includes all 10 categories
- Check `emails` collection has `classification_version: "3.0"`
- Verify OAuth callback triggered classification

### Facts not being extracted
- Ensure email category is in `IMPORTANT_CATEGORIES`
- Check `memory_facts` collection in MongoDB
- Verify background worker is running

---

## Future Improvements

- [ ] Personalized classification based on user behavior
- [ ] Machine learning model trained on user's past classifications
- [ ] Real-time WebSocket updates for new classifications
- [ ] Bulk category reassignment UI
- [ ] Custom category rules per user

---

**Last Updated:** Jan 6, 2026  
**Version:** 3.0  
**Status:** ✅ Production Ready

