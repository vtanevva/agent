# Automatic Backfill on User Onboarding

This guide explains how the system automatically backfills facts when users connect their accounts.

## 🎯 How It Works

### User Flow:
```
1. User opens app → Clicks "Connect Gmail"
   ↓
2. Google OAuth → User authorizes
   ↓
3. OAuth callback → Credentials saved
   ↓
4. 🎯 BACKFILL TRIGGERED (automatic!)
   ↓
5. Background job → Processes last 50 messages
   ↓
6. Facts extracted → User gets personalized experience
```

### Timeline:
```
00:00 - User authorizes Gmail
00:01 - OAuth callback completes
00:01 - Backfill job enqueued (non-blocking)
00:02 - Job starts processing messages
00:10 - Facts extracted (5-10 mins for 50 messages)
00:10 - User now has personalized facts! ✅
```

## 📋 What Gets Backfilled

When user connects:
- ✅ Last 50 email messages (configurable)
- ✅ Only incoming messages (user's emails, not bot responses)
- ✅ Facts extracted automatically
- ✅ Stored in MongoDB + Pinecone
- ❌ Does NOT block OAuth completion (runs in background)

## 🔧 Configuration

### Adjust Number of Messages

In `server.py` (line ~1435):

```python
# Change limit here:
"limit": 50,  # ← Increase to backfill more messages
```

### Skip Backfill for New Users

```python
if message_count > 10:  # Only backfill if user has 10+ messages
    # ... trigger backfill
```

### Backfill Different Channels

```python
# Backfill WhatsApp messages instead
message_count = messages_col.count_documents({
    "user_id": state,
    "channel": "whatsapp"  # Only WhatsApp
})
```

## 🧪 Testing Locally

### Test 1: Create Test Messages

```python
# Create test script: create_test_messages.py
from app.database import init_database
from app.memory.models import get_messages_collection
from datetime import datetime, timedelta

init_database()
messages_col = get_messages_collection()

# Create 20 test messages
for i in range(20):
    messages_col.insert_one({
        "_id": f"test-msg-{i}",
        "user_id": "test-user-123",
        "thread_id": "test-thread",
        "channel": "email",
        "direction": "in",
        "text": f"Test message {i}: I prefer morning meetings and work at TechCorp",
        "ts": datetime.utcnow() - timedelta(days=i),
        "meta": {}
    })

print("✅ Created 20 test messages")
```

### Test 2: Simulate OAuth Connection

```powershell
# Start server
python server.py

# In another terminal, simulate OAuth callback
# (This triggers backfill)
Invoke-RestMethod -Uri "http://localhost:10000/google/oauth2callback?state=test-user-123&code=fake-code"
```

### Test 3: Check Backfill Results

```powershell
# Wait 2 minutes for backfill
Start-Sleep -Seconds 120

# Check facts
Invoke-RestMethod -Uri "http://localhost:10000/memory/facts?user_id=test-user-123"
```

## 📊 Monitoring Backfill

### Check Server Logs

Look for these messages:

```
🔄 Triggering backfill for user test-user-123 (47 messages)
📥 Enqueued job: backfill-oauth-test-user-123
⚙️ Executing job: backfill-oauth-test-user-123
✅ Extracted 3 candidate facts from text
💾 Stored fact: User prefers morning meetings
✅ Backfill completed for user test-user-123
```

### API Endpoint to Check Status

```powershell
# Check user's facts
Invoke-RestMethod -Uri "http://localhost:10000/memory/facts?user_id=USER_ID"

# Check user's context
Invoke-RestMethod -Uri "http://localhost:10000/memory/context?user_id=USER_ID"
```

## 🎨 Custom Backfill Strategies

### Strategy 1: Immediate Backfill (Small Batch)

```python
# In OAuth callback
requests.post(
    "http://localhost:10000/memory/admin/backfill-facts",
    json={"user_id": state, "limit": 10}  # Only 10 messages, fast!
)
```

### Strategy 2: Progressive Backfill

```python
# Backfill in stages
def progressive_backfill(user_id):
    # Stage 1: Last 10 messages (immediate)
    requests.post(".../backfill-facts", json={"user_id": user_id, "limit": 10})
    
    # Stage 2: Next 40 messages (after 5 mins)
    time.sleep(300)
    requests.post(".../backfill-facts", json={"user_id": user_id, "limit": 50})
    
    # Stage 3: Full history (after 1 hour)
    time.sleep(3600)
    requests.post(".../backfill-facts", json={"user_id": user_id, "limit": 200})
```

### Strategy 3: Priority Messages

```python
# Only backfill important messages (starred, flagged, etc.)
messages = messages_col.find({
    "user_id": user_id,
    "meta.importance": "high"  # Custom flag
})
```

## ⚠️ Production Considerations

### 1. Rate Limiting

```python
# Limit backfill to prevent LLM API overload
MAX_BACKFILL_PER_HOUR = 100

# Track backfills in Redis/MongoDB
if get_recent_backfills_count() > MAX_BACKFILL_PER_HOUR:
    logger.warning("Backfill rate limit reached, queueing for later")
    return
```

### 2. Cost Control

```python
# Calculate estimated cost before backfill
message_count = 50
estimated_cost = message_count * 0.001  # ~$0.001 per message

if estimated_cost > 0.10:  # More than $0.10
    logger.warning(f"High backfill cost: ${estimated_cost}")
    # Send notification to admin
```

### 3. User Notification

```python
# Notify user that personalization is in progress
send_notification(user_id, {
    "type": "backfill_started",
    "message": "Aivis is learning from your messages...",
    "estimated_time": "5-10 minutes"
})

# After completion
send_notification(user_id, {
    "type": "backfill_complete",
    "message": "Ready! I now remember your preferences.",
    "facts_count": 12
})
```

## 🚀 Deployment Checklist

When deploying to Railway:

- [x] OAuth callback updated with backfill integration
- [ ] Environment variables set:
  - `PINECONE_API_KEY`
  - `OPENAI_API_KEY`
  - `MONGO_URI`
- [ ] Test OAuth flow in production
- [ ] Monitor first few backfills
- [ ] Check LLM API costs
- [ ] Adjust `limit` based on performance

## 📈 Expected Results

### Before Backfill:
```
User connects → No facts → Generic responses
"Hello!" → "Hi! How can I help you?"
```

### After Backfill:
```
User connects → Facts extracted → Personalized responses
"Hello!" → "Hi! Ready to help with your morning meetings at TechCorp!"
```

## 🎯 Success Metrics

Track these metrics:

1. **Backfill completion rate**: % of users with facts after OAuth
2. **Average facts per user**: Should be 5-15 facts
3. **Backfill time**: Should complete within 10 minutes
4. **User engagement**: Do users with facts engage more?
5. **Cost per user**: LLM costs for backfill

## 💡 Tips

1. **Start small**: Use `limit: 10` initially, then increase
2. **Monitor costs**: Watch OpenAI API usage
3. **Log everything**: Track backfill success/failure
4. **Test locally first**: Before deploying to production
5. **Have fallback**: If backfill fails, app still works

---

## 🆘 Troubleshooting

### Issue: Backfill not triggering

**Check:**
1. Is background job queue running? Look for "Started N background workers"
2. Are there messages in DB? Check `messages_col.count_documents()`
3. Check logs for errors

**Fix:**
```python
# Add more logging
logger.info(f"Message count for {state}: {message_count}")
logger.info(f"Enqueueing backfill job...")
```

### Issue: Backfill too slow

**Solutions:**
1. Reduce `limit` to 20-30 messages
2. Use progressive backfill (small batch first)
3. Increase background workers

### Issue: Facts not appearing

**Check:**
1. Wait 10 minutes for processing
2. Check OpenAI API key is valid
3. Look for fact extraction logs
4. Query facts API manually

## 📚 Related Docs

- [USER_AWARENESS.md](USER_AWARENESS.md) - Full system guide
- [RUNBOOK_USER_AWARENESS.md](RUNBOOK_USER_AWARENESS.md) - Testing guide
- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) - Integration examples

---

**Summary**: Users connecting their accounts automatically get facts backfilled from their last 50 messages, giving them a personalized experience from day 1! 🎉

