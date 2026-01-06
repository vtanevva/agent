# User Awareness Deployment Guide

Complete step-by-step guide for deploying the User Awareness system to production.

## 📋 Deployment Phases

### Phase 1: Pre-Deployment Setup (Day -7 to Day -1)

#### 1.1 Environment Configuration

**Production `.env` file:**
```bash
# LLM & Embeddings
OPENAI_API_KEY=sk-prod-your-production-key-here
EMBEDDING_MODEL=text-embedding-ada-002
OPENAI_MODEL=gpt-4o-mini

# Database
MONGO_URI=mongodb+srv://prod-user:password@cluster.mongodb.net/aivis-prod
MONGO_DB_NAME=aivis-production

# Vector Database
PINECONE_API_KEY=pcsk-prod-your-production-key-here
PINECONE_INDEX_NAME=aivis-memory-prod
PINECONE_ENV=us-east-1

# Feature Flags
ENABLE_MEMORY=true
ENABLE_RAG=true

# App Settings
APP_ENV=production
FLASK_SECRET_KEY=your-strong-random-secret-key
UPLOAD_FOLDER=/var/app/uploads
PORT=10000

# Logging
LOG_LEVEL=INFO
```

#### 1.2 Create Production Resources

**1. MongoDB Setup:**
```bash
# Create production database
# Create collections (will be auto-created on first run)
# Set up proper indexes (handled by app on startup)
```

**2. Pinecone Setup:**
```python
# Create production index (one-time setup)
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="your-prod-key")
pc.create_index(
    name="aivis-memory-prod",
    dimension=1536,
    metric="cosine",
    spec=ServerlessSpec(
        cloud="aws",
        region="us-east-1"
    )
)
```

**3. File Storage:**
```bash
# Create uploads directory
mkdir -p /var/app/uploads
chmod 755 /var/app/uploads

# Set up backup/cleanup cron job
# Cleanup files older than 90 days
0 2 * * * find /var/app/uploads -type f -mtime +90 -delete
```

#### 1.3 Run Setup Script

```bash
# Test connection to all services
python scripts/setup_memory_system.py
```

Expected output:
```
✅ Environment Variables
✅ MongoDB Connection
✅ MongoDB Indexes
✅ Pinecone Connection
✅ Embedding Generation
✅ Upload Folder
```

### Phase 2: Initial Deployment (Day 0)

#### 2.1 Deploy Application

**Option A: Docker Deployment**
```bash
# Build image
docker build -t aivis-app:latest .

# Run container
docker run -d \
  --name aivis \
  --env-file .env \
  -p 10000:10000 \
  -v /var/app/uploads:/app/uploads \
  aivis-app:latest
```

**Option B: Direct Deployment**
```bash
# Pull latest code
git pull origin main

# Install dependencies
pip install -r requirements.txt

# Start server
gunicorn -w 4 -b 0.0.0.0:10000 server:app
```

#### 2.2 Verify Deployment

```bash
# Test health endpoint
curl http://localhost:10000/memory/health

# Expected response:
{
  "success": true,
  "status": "healthy",
  "components": {
    "database": "connected",
    "vector_store": "initialized"
  }
}
```

#### 2.3 Deploy Without Processing Old Messages

⚠️ **IMPORTANT**: On initial deployment:
- **DO NOT run backfill immediately**
- Let system stabilize for 24-48 hours
- Monitor for errors and performance issues
- Only NEW messages will have facts extracted

**Why?**
```
Day 0: Deploy → Only NEW messages processed ✅
  ├─ System is stable
  ├─ No sudden LLM API costs
  └─ Can monitor for issues

Day 2: After stability confirmed → Run backfill
  ├─ Process historical messages
  └─ Controlled, monitored process
```

### Phase 3: Post-Deployment Stabilization (Day 1-2)

#### 3.1 Monitor System

**Check logs for:**
```bash
# Successful fact extraction
✅ Extracted N candidate facts
💾 Stored fact: User prefers morning meetings

# Vector store operations
✅ Upserted N vectors for user
🔍 Vector search for user

# No errors
❌ Check for any errors or exceptions
```

**Monitor metrics:**
- Message ingestion rate
- Fact extraction success rate
- Vector search latency
- LLM API costs

#### 3.2 Test with Real Users

**Smoke tests:**
```bash
# 1. Send test message
curl -X POST http://localhost:10000/memory/ingest-message \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-prod-user",
    "thread_id": "test-thread",
    "channel": "test",
    "direction": "in",
    "text": "I prefer morning meetings and work at TechCorp"
  }'

# 2. Wait 10 seconds for background processing
sleep 10

# 3. Check facts were extracted
curl "http://localhost:10000/memory/facts?user_id=test-prod-user"

# 4. Test context retrieval
curl "http://localhost:10000/memory/context?user_id=test-prod-user&q=work"
```

### Phase 4: Historical Data Backfill (Day 3+)

⚠️ **Only proceed if Phase 3 is stable!**

#### 4.1 Plan Backfill Strategy

**Calculate scope:**
```python
# Count messages to backfill
from app.memory.models import get_messages_collection

messages_col = get_messages_collection()
total_messages = messages_col.count_documents({"direction": "in"})
users_count = len(messages_col.distinct("user_id"))

print(f"Total messages: {total_messages}")
print(f"Total users: {users_count}")
print(f"Avg per user: {total_messages / users_count}")

# Estimate costs (GPT-4o-mini)
# ~$0.001 per message for fact extraction
estimated_cost = total_messages * 0.001
print(f"Estimated cost: ${estimated_cost:.2f}")
```

**Choose strategy:**

| Users | Messages/User | Strategy | Timeline |
|-------|--------------|----------|----------|
| < 100 | < 1000 | Full backfill | 1-2 hours |
| < 1000 | < 500 | Batch by user | 1 day |
| > 1000 | Any | Incremental | 1 week |

#### 4.2 Incremental Backfill (Recommended)

**Day 3: Test with small batch**
```bash
# Test with 1 user, 10 messages
python scripts/backfill_facts.py --user-id "power-user-123" --limit 10

# Monitor:
# - Processing time
# - Fact quality
# - Any errors
```

**Day 4: Expand to active users**
```bash
# Process 50 most recent messages for active users
python scripts/backfill_facts.py --limit 50

# Monitor:
# - LLM API costs
# - Database load
# - Processing time
```

**Day 5-7: Full backfill**
```bash
# Process all messages in batches
# Use cron job to run during off-hours

# Crontab entry (2 AM daily):
0 2 * * * cd /var/app && python scripts/backfill_facts.py --limit 100 >> /var/log/backfill.log 2>&1
```

#### 4.3 Monitor Backfill Progress

**Check progress:**
```python
from app.memory.models import (
    get_messages_collection,
    get_memory_facts_collection
)

messages_col = get_messages_collection()
facts_col = get_memory_facts_collection()

# Total messages
total_msgs = messages_col.count_documents({"direction": "in"})

# Total facts
total_facts = facts_col.count_documents({"is_active": True})

# Facts per user
users = facts_col.distinct("user_id")
avg_facts = total_facts / len(users) if users else 0

print(f"Messages: {total_msgs}")
print(f"Facts: {total_facts}")
print(f"Users with facts: {len(users)}")
print(f"Avg facts/user: {avg_facts:.1f}")
```

**Stop backfill when:**
- ✅ All active users have facts
- ✅ Recent messages (last 30 days) processed
- ✅ Costs are within budget

### Phase 5: Integration with Existing Features

#### 5.1 Update Chat Endpoint

**Before (no memory):**
```python
@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json['message']
    response = llm_service.call_llm([
        {"role": "user", "content": user_msg}
    ])
    return jsonify({"response": response})
```

**After (with memory):**
```python
@app.route('/chat', methods=['POST'])
def chat():
    from app.memory.prompt_builder import build_context_aware_messages
    from app.memory.ingestion_service import get_ingestion_service
    from app.memory.models import MessageDirection
    
    user_id = request.json['user_id']
    thread_id = request.json.get('thread_id', 'default')
    user_msg = request.json['message']
    
    # Build context-aware messages
    messages = build_context_aware_messages(
        user_id=user_id,
        thread_id=thread_id,
        user_message=user_msg,
    )
    
    # Generate response
    response = llm_service.call_llm(messages)
    
    # Store conversation
    ingestion = get_ingestion_service()
    ingestion.ingest_message(
        user_id=user_id,
        thread_id=thread_id,
        channel='web_chat',
        direction=MessageDirection.INCOMING,
        text=user_msg,
    )
    ingestion.ingest_message(
        user_id=user_id,
        thread_id=thread_id,
        channel='web_chat',
        direction=MessageDirection.OUTGOING,
        text=response,
    )
    
    return jsonify({"response": response})
```

#### 5.2 Update Email Handler

```python
@app.route('/webhook/email', methods=['POST'])
def email_webhook():
    from app.memory.ingestion_service import get_ingestion_service
    from app.memory.prompt_builder import build_context_aware_messages
    from app.memory.models import MessageDirection
    
    email_data = request.json
    user_id = email_data['user_id']
    thread_id = email_data['thread_id']
    email_text = email_data['body']
    
    # Ingest email
    ingestion = get_ingestion_service()
    ingestion.ingest_message(
        user_id=user_id,
        thread_id=thread_id,
        channel='email',
        direction=MessageDirection.INCOMING,
        text=email_text,
        source_id=email_data['email_id'],
        extract_facts=True,
    )
    
    # Generate context-aware reply
    messages = build_context_aware_messages(
        user_id=user_id,
        thread_id=thread_id,
        user_message=f"Draft a reply to: {email_text}",
    )
    
    reply = llm_service.call_llm(messages)
    
    return jsonify({"reply": reply})
```

#### 5.3 Update WhatsApp Handler

```python
@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    # Similar to email handler
    # Use channel='whatsapp'
    pass
```

### Phase 6: Ongoing Maintenance

#### 6.1 Automated Backfill (Cron Job)

**Setup cron job for continuous backfill:**
```bash
# /etc/cron.d/aivis-backfill
# Run backfill daily at 2 AM
0 2 * * * appuser cd /var/app && /var/app/.venv/bin/python scripts/backfill_facts.py --limit 50 >> /var/log/aivis-backfill.log 2>&1
```

**Or use systemd timer:**
```bash
# /etc/systemd/system/aivis-backfill.service
[Unit]
Description=Aivis Fact Backfill Service

[Service]
Type=oneshot
User=appuser
WorkingDirectory=/var/app
ExecStart=/var/app/.venv/bin/python scripts/backfill_facts.py --limit 50
StandardOutput=append:/var/log/aivis-backfill.log
StandardError=append:/var/log/aivis-backfill.log

# /etc/systemd/system/aivis-backfill.timer
[Unit]
Description=Run Aivis Backfill Daily

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
systemctl enable aivis-backfill.timer
systemctl start aivis-backfill.timer
```

#### 6.2 Monitoring Dashboard

**Key metrics to track:**
```python
# scripts/monitoring_stats.py
from app.memory.models import (
    get_messages_collection,
    get_memory_facts_collection,
    get_documents_collection
)
from app.memory.vector_store import get_vector_store

def get_memory_stats():
    msgs = get_messages_collection()
    facts = get_memory_facts_collection()
    docs = get_documents_collection()
    vector_store = get_vector_store()
    
    return {
        "total_messages": msgs.count_documents({}),
        "total_facts": facts.count_documents({"is_active": True}),
        "total_documents": docs.count_documents({}),
        "users_with_facts": len(facts.distinct("user_id")),
        "avg_facts_per_user": facts.count_documents({}) / len(facts.distinct("user_id")),
    }
```

#### 6.3 Regular Maintenance Tasks

**Weekly:**
- Review fact extraction quality
- Check for extraction errors
- Monitor LLM API costs
- Review user feedback

**Monthly:**
- Clean up inactive facts
- Optimize vector store
- Review and tune confidence thresholds
- Update extraction prompts if needed

**Quarterly:**
- Full backfill for new users
- Re-process messages with improved logic
- Archive old data

## 🔄 Rollback Plan

If issues occur:

**1. Disable memory system:**
```bash
# In .env
ENABLE_MEMORY=false

# Restart server
systemctl restart aivis
```

**2. App continues without memory features:**
- Chat still works (no context)
- Email still works (no personalization)
- No errors or crashes

**3. Fix and redeploy:**
- Fix issues
- Test in staging
- Re-enable: `ENABLE_MEMORY=true`

## 📊 Success Criteria

After 2 weeks:
- ✅ 90%+ of active users have facts
- ✅ < 5% fact extraction errors
- ✅ Context retrieval < 500ms
- ✅ Users report improved personalization
- ✅ LLM costs within budget

## 🎯 Summary Timeline

```
Day -7: Setup production resources
Day -1: Deploy to staging, test
Day 0:  Deploy to production (new messages only)
Day 1:  Monitor and stabilize
Day 2:  Continue monitoring
Day 3:  Test backfill with 1 user
Day 4:  Backfill active users
Day 5-7: Full backfill (gradual)
Week 2: Monitor and optimize
Week 3: Integrate with all features
Week 4: Production ready, maintenance mode
```

## ✅ Deployment Checklist

Use `DEPLOYMENT_CHECKLIST.md` for detailed pre-deployment checks.

---

**Questions?** See:
- Quick Start: `QUICK_START.md`
- Testing: `docs/RUNBOOK_USER_AWARENESS.md`
- Architecture: `docs/USER_AWARENESS.md`

