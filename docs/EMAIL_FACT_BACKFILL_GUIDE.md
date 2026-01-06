# Email Fact Backfill Guide

Extract facts from your existing emails to build user context without storing sensitive email content.

## 📋 Overview

**What gets extracted:** User preferences, work style, context (e.g., "prefers morning meetings", "vegetarian")

**What's NOT stored:** Full email bodies, threads, attachments, recipient lists

## 🎯 Three Ways to Backfill

### **Option 1: API Endpoint** (Easiest - Use from Frontend)

Trigger via HTTP POST:

```bash
curl -X POST http://localhost:10000/memory/admin/backfill-email-facts \
  -H "Content-Type: application/json" \
  -d '{"user_id": "v", "max_emails": 100}'
```

**PowerShell:**
```powershell
Invoke-RestMethod -Uri "http://localhost:10000/memory/admin/backfill-email-facts" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"user_id": "v", "max_emails": 100}'
```

**Response:**
```json
{
  "success": true,
  "message": "Email fact backfill started in background",
  "user_id": "v",
  "max_emails": 100
}
```

---

### **Option 2: Simple Python Script** (Quick & Easy)

Process unclassified emails:

```bash
python scripts/backfill_email_facts.py
```

**Features:**
- Processes up to 100 unclassified emails
- Fast (uses existing classification system)
- Run multiple times to process more emails

**Edit the script** to change user or limit:
```python
# In scripts/backfill_email_facts.py
USER_ID = "v"  # Your user ID
MAX_EMAILS = 100  # Emails per run
```

---

### **Option 3: Comprehensive Python Script** (Process ALL Emails)

Process ALL emails (even already classified ones):

```bash
# Process all emails
python scripts/backfill_all_email_facts.py

# Custom user
python scripts/backfill_all_email_facts.py --user-id v

# Limit to 200 emails
python scripts/backfill_all_email_facts.py --max-emails 200

# Custom batch size
python scripts/backfill_all_email_facts.py --batch-size 100
```

**Features:**
- Processes ALL existing emails (classified or not)
- Batched processing (avoids rate limits)
- Progress tracking
- Configurable limits

---

## 📊 Monitoring Progress

### Check Server Logs

Look for these messages:

```
✅ PromptBuilder initialized
✅ Vector store initialized: psy
📧 Extracted 3 facts from email (user: v)
📧 Extracted and embedded 2 facts from email (user: v)
💾 Stored fact: User prefers morning meetings (type=preference)
```

### Check Extracted Facts

**Via API:**
```bash
curl http://localhost:10000/memory/facts?user_id=v
```

**PowerShell:**
```powershell
Invoke-WebRequest -Uri "http://localhost:10000/memory/facts?user_id=v" | 
  ConvertFrom-Json | 
  Select-Object -ExpandProperty facts | 
  Format-Table text, type, confidence, created_at
```

**Via MongoDB:**
```javascript
db.memory_facts.find({ 
  user_id: "v", 
  is_active: true,
  source_ref: { $regex: "^email:" }
})
```

---

## ⚙️ Configuration

### Adjust Batch Size

In `scripts/backfill_all_email_facts.py`:
```python
batch_size = 50  # Process 50 emails at a time
```

**Smaller batch** = More frequent progress updates, slower  
**Larger batch** = Faster processing, less frequent updates

### Limit Emails

```bash
# Process only 100 emails (testing)
python scripts/backfill_all_email_facts.py --max-emails 100

# Process all emails (production)
python scripts/backfill_all_email_facts.py
```

---

## 🔄 How It Works

```
1. Fetch emails from MongoDB
   ↓
2. For each email:
   - Extract subject, sender, snippet (NOT full body!)
   - Pass to LLM for fact extraction
   - LLM returns: "User prefers morning meetings"
   ↓
3. Store facts:
   - MongoDB (memory_facts collection)
   - Pinecone (vector embeddings for search)
   ↓
4. Discard email content
   ✅ Only facts remain!
```

---

## 💰 Cost Estimation

**Per email:**
- 1 LLM call (fact extraction) ≈ $0.0001
- 1-3 embedding calls (per fact) ≈ $0.00001 each

**Example:**
- 1000 emails × $0.0001 = **$0.10**
- 3000 emails × $0.0001 = **$0.30**

Most emails yield 0-2 facts, so not every email extracts facts.

---

## 🚨 Troubleshooting

### No Facts Extracted

**Check:**
1. Are emails in MongoDB? (Run inbox sync first)
2. Check server logs for errors
3. Verify OpenAI API key is valid
4. Check email content (transactional emails rarely have facts)

### "Database not connected"

**Fix:**
```bash
# Check MongoDB connection in .env
MONGO_URI=mongodb://localhost:27017/aivis
```

### Rate Limits

**Reduce batch size:**
```bash
python scripts/backfill_all_email_facts.py --batch-size 25
```

**Add delays between batches** (edit script):
```python
time.sleep(5)  # Wait 5 seconds between batches
```

---

## 📈 Best Practices

### First Run
1. Start with a **small limit** (e.g., 50 emails) to test
2. Check extracted facts for quality
3. Adjust and run full backfill

### Production
1. Run during **off-peak hours** (lower API costs)
2. Process in **batches** (avoid rate limits)
3. **Monitor logs** for errors
4. Run **periodically** for new emails

### Privacy
- Only stable facts are stored (preferences, context)
- Transient information is filtered (dates, tasks)
- Full email bodies are NEVER stored
- Check extracted facts regularly: `GET /memory/facts?user_id=v`

---

## 🎯 Integration with Onboarding

Trigger backfill when user connects Google account:

```python
# In server.py or oauth callback
@app.route("/auth/google/callback")
def google_callback():
    # ... OAuth flow ...
    
    # Trigger email fact backfill
    import threading
    from app.services.gmail_service import classify_background
    
    def backfill():
        classify_background(user_id, max_emails=100)
    
    threading.Thread(target=backfill, daemon=True).start()
    
    return redirect("/")
```

---

## ✅ Verification

After running backfill:

```bash
# 1. Check fact count
curl http://localhost:10000/memory/facts?user_id=v | jq '.count'

# 2. View sample facts
curl http://localhost:10000/memory/facts?user_id=v | jq '.facts[0:5]'

# 3. Test retrieval in chat
# Send message: "When should we schedule a meeting?"
# AI should use stored preference: "Based on your preference for morning meetings..."
```

---

## 📚 Related Docs

- [User Awareness System](./USER_AWARENESS.md)
- [Integration Guide](./INTEGRATION_GUIDE.md)
- [Memory API Routes](../app/api/memory_routes.py)

