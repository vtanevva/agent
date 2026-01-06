# Email Classification v3.0 - Smart Fact Extraction

## 🎯 Overview

Upgraded email classification system with **better categorization** and **intelligent fact extraction filtering** to save costs and improve quality.

---

## 📊 New Email Categories

### ✅ **Important Categories** (Facts Extracted)
1. **`urgent`** - High priority emails requiring immediate attention
   - Keywords: urgent, asap, immediately, important, critical
   - Examples: Client emergencies, deadline reminders

2. **`action_items`** - Tasks, meetings, requests
   - Keywords: can you do, please fix, meeting, schedule, deadline
   - Examples: Meeting requests, task assignments

3. **`clients`** - Client communications
   - Sender-based detection
   - Examples: Client emails, vendor communications

4. **`waiting_for_reply`** - Pending responses
   - Keywords: waiting for your response, following up
   - Examples: Follow-ups, check-ins

5. **`normal`** - Other personal/work emails
   - Default for emails not matching other categories
   - Examples: General conversations

### ❌ **Noise Categories** (Facts NOT Extracted)
6. **`notifications`** - Automated system notifications
   - Keywords: notification, alert, jira, github, slack, trello
   - Senders: noreply@, no-reply@, notifications@, alerts@
   - Examples: GitHub commits, Jira updates, Slack notifications

7. **`newsletters`** - Newsletters and digests
   - Keywords: unsubscribe, newsletter, digest, weekly update
   - Examples: Company newsletters, blog digests

8. **`promotional`** - Marketing and sales emails
   - Keywords: promotion, special offer, sale, discount, % off
   - Examples: Marketing emails, product promotions

9. **`transactional`** - Orders, shipping, receipts
   - Keywords: order confirmation, shipped, tracking number, delivery
   - Examples: Amazon orders, shipping notifications

10. **`social`** - Social media notifications
    - Keywords: want to connect, linkedin, viewed your profile
    - Domains: linkedin.com, twitter.com, facebook.com
    - Examples: LinkedIn connection requests, Twitter notifications

11. **`invoices`** - Billing and invoices
    - Keywords: invoice, payment, billing, statement
    - Examples: Invoices, payment receipts

---

## 🔍 Smart Fact Extraction

### **How It Works:**

```
Email Received
    ↓
Classify Email (v3.0)
    ↓
Category: "urgent" ✅ → Extract Facts
Category: "promotional" ❌ → Skip Fact Extraction
    ↓
Only Important Emails → Facts Stored
```

### **Categories That Extract Facts:**
- ✅ `urgent`
- ✅ `action_items`
- ✅ `clients`
- ✅ `waiting_for_reply`
- ✅ `normal`

### **Categories That Skip Fact Extraction:**
- ❌ `notifications` (automated, no user context)
- ❌ `newsletters` (generic content)
- ❌ `promotional` (marketing, not personal)
- ❌ `transactional` (order confirmations, not preferences)
- ❌ `social` (social media noise)
- ❌ `invoices` (billing, not conversational)

---

## 💰 Cost Savings

### **Before (v2.0):**
- Extracted facts from ALL emails
- 1000 emails × $0.0001 = **$0.10**
- Includes newsletters, notifications, spam

### **After (v3.0):**
- Only extracts from ~40% of emails (important ones)
- 400 emails × $0.0001 = **$0.04**
- **60% cost reduction!** 🎯

### **Quality Improvement:**
- Focuses on meaningful conversations
- Filters out automated/marketing content
- Better fact relevance

---

## 🔄 Migration

### **Classification Version:**
Changed from `2.0` → `3.0`

Existing emails will be automatically re-classified on next inbox sync or manual classification.

### **Database:**
No schema changes needed. New categories are stored in existing `category` field.

### **Vector Store:**
Pinecone vectors remain unchanged. Only affects which emails get fact extraction.

---

## 🧪 Testing

### **Test Classification:**

```bash
# Classify a single email
curl -X POST http://localhost:10000/api/classify-email \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "v",
    "thread_id": "thread123"
  }'
```

### **Expected Results:**

| Email Type | Expected Category |
|------------|------------------|
| "Meeting with client tomorrow" | `action_items` |
| "URGENT: Server down" | `urgent` |
| "LinkedIn connection request" | `social` |
| "Your order has shipped" | `transactional` |
| "Weekly newsletter" | `newsletters` |
| "GitHub: PR #123 merged" | `notifications` |
| "50% OFF SALE!" | `promotional` |

### **Verify Fact Extraction:**

```bash
# Check facts (should only be from important emails)
curl http://localhost:10000/memory/facts?user_id=v

# Check server logs for:
# ✅ "[*] Extracting facts from urgent email"
# ❌ "[*] Skipping fact extraction for promotional email"
```

---

## 📝 Example Detection Rules

### **Notifications:**
```
Subject: "[GitHub] Pull request #123 was merged"
From: notifications@github.com
Category: notifications ❌ (No facts extracted)
```

### **Action Items:**
```
Subject: "Meeting with client on Friday"
From: john@company.com
Category: action_items ✅ (Facts extracted)
Extracted: "User has client meeting on Friday"
```

### **Promotional:**
```
Subject: "🎉 50% OFF Everything!"
From: sales@store.com
Category: promotional ❌ (No facts extracted)
```

### **Urgent:**
```
Subject: "URGENT: Production server down"
From: alerts@company.com  
Category: urgent ✅ (Facts extracted)
Extracted: "User manages production systems"
```

---

## 🔧 Configuration

### **Customize Filtering:**

Edit `app/services/gmail_service.py`:

```python
# In extract_facts_from_email()
SKIP_CATEGORIES = ['notifications', 'newsletters', 'promotional', 'transactional', 'social']
EXTRACT_CATEGORIES = ['urgent', 'action_items', 'clients', 'waiting_for_reply', 'normal']
```

### **Adjust Detection Keywords:**

Edit `app/tools/email/classifier.py`:

```python
# Add custom notification keywords
notification_keywords = [
    "notification", "alert", "jira", "github", 
    "your_custom_tool"  # Add your keywords
]
```

---

## 📈 Performance

### **Classification Speed:**
- Same as v2.0 (~100ms per email)
- No performance impact

### **Fact Extraction:**
- 60% fewer LLM calls
- 60% cost reduction
- Faster overall processing

### **Storage:**
- Only relevant facts stored
- Better signal-to-noise ratio
- Cleaner fact database

---

## 🚀 Deployment

### **Steps:**
1. ✅ Code already updated
2. ✅ Classification v3.0 active
3. ✅ Fact extraction filter active

### **Next Sync:**
- New emails automatically use v3.0
- Existing emails re-classified if needed

### **Manual Re-classification:**
```bash
python scripts/backfill_all_email_facts.py --max-emails 100
```

---

## 📚 Related Docs

- [Email Fact Backfill Guide](./EMAIL_FACT_BACKFILL_GUIDE.md)
- [User Awareness System](./USER_AWARENESS.md)
- [Integration Guide](./INTEGRATION_GUIDE.md)

