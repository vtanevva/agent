# User Awareness Integration Guide

How to integrate the User Awareness system into your existing Aivis application.

## 🎯 Integration Strategy

### The Big Picture

```
┌─────────────────────────────────────────────────────────────┐
│ BEFORE: Traditional Chatbot                                  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  User: "What are my preferences?"                            │
│     ↓                                                         │
│  LLM: "I don't have information about your preferences"      │
│     ↓                                                         │
│  ❌ Generic response, no personalization                     │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ AFTER: User Awareness Enabled                                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  User: "What are my preferences?"                            │
│     ↓                                                         │
│  Memory System retrieves:                                    │
│    - "User prefers morning meetings"                         │
│    - "User likes async communication"                        │
│    - "User works at TechCorp"                                │
│     ↓                                                         │
│  LLM: "Based on your history, you prefer morning meetings    │
│        and async communication over phone calls..."          │
│     ↓                                                         │
│  ✅ Personalized response with context                       │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 When to Use Backfill Script

### Decision Tree

```
Are you deploying for the first time?
├─ YES → Don't run backfill immediately
│         ├─ Deploy system
│         ├─ Let it stabilize (48 hours)
│         ├─ Monitor new messages
│         └─ THEN run backfill (Day 3+)
│
└─ NO → Is the system already running?
          ├─ YES → Run backfill for:
          │         ├─ New users
          │         ├─ Missing facts
          │         └─ Re-processing
          │
          └─ NO → Follow deployment guide
```

### Scenarios When You SHOULD Run Backfill

#### 1. **After Initial Deployment** (Day 3+)
```bash
# System is stable, now process historical messages
python scripts/backfill_facts.py --limit 100
```

**Why:** Old messages before deployment have no facts.

#### 2. **New User Onboarded**
```bash
# User just signed up, has 50 old messages
python scripts/backfill_facts.py --user-id "new-user-123" --limit 50
```

**Why:** Give new users immediate personalization.

#### 3. **Background Jobs Failed**
```bash
# Facts weren't extracted due to API issues
python scripts/backfill_facts.py --user-id "user-123" --limit 20
```

**Why:** Fix missing facts from recent messages.

#### 4. **Improved Extraction Logic**
```bash
# You improved the fact extraction prompt
python scripts/backfill_facts.py --limit 100
```

**Why:** Re-process messages with better extraction.

### Scenarios When You SHOULD NOT Run Backfill

#### ❌ 1. **Day 0 Deployment**
```bash
# DON'T DO THIS on deployment day
python scripts/backfill_facts.py --limit 1000  # ❌ BAD
```

**Why:** System not stabilized, risks overwhelming LLM API.

#### ❌ 2. **Testing/Development**
```bash
# Don't backfill in dev environment
python scripts/backfill_facts.py  # ❌ Use test data instead
```

**Why:** Use test fixtures, not production data.

#### ❌ 3. **Without Budget Check**
```bash
# 10,000 messages × $0.001 = $10
python scripts/backfill_facts.py --limit 10000  # ❌ Check costs first!
```

**Why:** LLM API costs can add up quickly.

## 📝 Integration Steps

### Step 1: Enable Memory System (Already Done ✅)

The system is integrated in `server.py`:
- ✅ Blueprint registered
- ✅ Indexes created on startup
- ✅ All endpoints available

### Step 2: Update Your Endpoints

#### Option A: Minimal Integration (Quick Start)

Just use the one-liner:

```python
# In your existing chat endpoint
from app.memory.prompt_builder import build_context_aware_messages

@app.route('/chat', methods=['POST'])
def chat():
    user_id = request.json['user_id']
    user_message = request.json['message']
    
    # OLD CODE:
    # messages = [{"role": "user", "content": user_message}]
    
    # NEW CODE (one line change):
    messages = build_context_aware_messages(
        user_id=user_id,
        thread_id=request.json.get('thread_id', 'default'),
        user_message=user_message
    )
    
    # Rest stays the same
    response = llm_service.call_llm(messages)
    return jsonify({"response": response})
```

**That's it!** Context is automatically injected.

#### Option B: Full Integration (Recommended)

Include message storage:

```python
from app.memory.prompt_builder import build_context_aware_messages
from app.memory.ingestion_service import get_ingestion_service
from app.memory.models import MessageDirection

@app.route('/chat', methods=['POST'])
def chat():
    user_id = request.json['user_id']
    thread_id = request.json.get('thread_id', 'default')
    user_message = request.json['message']
    
    # 1. Build context-aware messages
    messages = build_context_aware_messages(
        user_id=user_id,
        thread_id=thread_id,
        user_message=user_message
    )
    
    # 2. Generate response
    response = llm_service.call_llm(messages)
    
    # 3. Store conversation (for future context)
    ingestion = get_ingestion_service()
    
    # Store user message
    ingestion.ingest_message(
        user_id=user_id,
        thread_id=thread_id,
        channel='web_chat',
        direction=MessageDirection.INCOMING,
        text=user_message,
        extract_facts=True,  # Extract facts in background
    )
    
    # Store bot response
    ingestion.ingest_message(
        user_id=user_id,
        thread_id=thread_id,
        channel='web_chat',
        direction=MessageDirection.OUTGOING,
        text=response,
        extract_facts=False,  # Don't extract from bot
    )
    
    return jsonify({"response": response})
```

### Step 3: Setup Continuous Backfill (Optional but Recommended)

For production, set up automatic backfill:

```bash
# Add to crontab
crontab -e

# Run backfill daily at 2 AM for recent messages
0 2 * * * cd /path/to/app && python scripts/backfill_facts.py --limit 50 >> /var/log/backfill.log 2>&1
```

This ensures:
- New users get facts extracted
- Failed extractions are retried
- System stays up-to-date

## 🚦 Deployment Workflow

### Development Environment

```bash
# 1. Test with sample data
python test_memory_manual.py

# 2. No backfill needed (use test fixtures)
```

### Staging Environment

```bash
# 1. Deploy code
git pull origin main
pip install -r requirements.txt

# 2. Run setup
python scripts/setup_memory_system.py

# 3. Start server
python server.py

# 4. Test with staging data
.\test_simple.ps1

# 5. Small backfill test (10 messages)
python scripts/backfill_facts.py --limit 10
```

### Production Environment

```bash
# Day 0: Deploy
git pull origin main
pip install -r requirements.txt
python scripts/setup_memory_system.py
systemctl restart aivis

# Day 1-2: Monitor
# - Watch logs
# - Check new messages are processed
# - Verify no errors

# Day 3: Start backfill (gradual)
python scripts/backfill_facts.py --limit 50

# Day 4-7: Expand backfill
python scripts/backfill_facts.py --limit 100

# Week 2+: Automate
# Add to cron for ongoing maintenance
```

## 📊 Integration Checklist

### Pre-Integration
- [ ] Read `QUICK_START.md`
- [ ] Run `setup_memory_system.py`
- [ ] Test with `test_simple.ps1`
- [ ] Verify health endpoint works

### Code Integration
- [ ] Update chat endpoint with `build_context_aware_messages()`
- [ ] Add message ingestion with `ingest_message()`
- [ ] Update email handler (if applicable)
- [ ] Update WhatsApp handler (if applicable)

### Deployment
- [ ] Deploy to staging first
- [ ] Test thoroughly
- [ ] Deploy to production
- [ ] Monitor for 48 hours
- [ ] DON'T run backfill immediately

### Post-Deployment (Day 3+)
- [ ] Run small backfill test (`--limit 10`)
- [ ] Monitor costs and performance
- [ ] Expand backfill gradually
- [ ] Set up automated backfill cron job

### Ongoing
- [ ] Monitor fact extraction quality
- [ ] Review LLM API costs
- [ ] Tune confidence thresholds
- [ ] Update extraction prompts as needed

## 🎯 Quick Reference

### When to Run Backfill

| Situation | Command | When |
|-----------|---------|------|
| Initial deployment | `python scripts/backfill_facts.py --limit 100` | Day 3+ |
| New user | `python scripts/backfill_facts.py --user-id USER --limit 50` | Immediately |
| Failed extraction | `python scripts/backfill_facts.py --user-id USER --limit 20` | Anytime |
| Improved logic | `python scripts/backfill_facts.py --limit 100` | After changes |
| Routine maintenance | Cron job | Daily at 2 AM |

### Integration Patterns

**Pattern 1: Minimal (Context only)**
```python
messages = build_context_aware_messages(user_id, thread_id, user_message)
response = llm_service.call_llm(messages)
```

**Pattern 2: Full (Context + Storage)**
```python
messages = build_context_aware_messages(user_id, thread_id, user_message)
response = llm_service.call_llm(messages)
ingestion.ingest_message(...)  # Store for future context
```

**Pattern 3: Custom (Manual control)**
```python
bundle = retrieval.retrieve_context(user_id, thread_id, query)
messages = builder.build_messages_with_context(bundle, user_message)
response = llm_service.call_llm(messages)
```

## 🆘 Troubleshooting

### "Should I run backfill now?"

**Ask yourself:**
1. Is the system stable? (48+ hours) → YES: Continue
2. Have I tested with new messages? → YES: Continue  
3. Do I have budget for LLM calls? → YES: Continue
4. Have I tested on 1 user first? → YES: Run full backfill

If any answer is NO → Wait or test more.

### "Backfill is taking too long"

```bash
# Reduce batch size
python scripts/backfill_facts.py --limit 20

# Or process one user at a time
python scripts/backfill_facts.py --user-id "user-123" --limit 50
```

### "Facts aren't being extracted"

Check:
1. OpenAI API key is valid
2. Background workers started (check logs)
3. Message length > 20 characters
4. Wait 10 seconds after ingestion

## 📚 Additional Resources

- **Deployment**: `docs/DEPLOYMENT_GUIDE.md`
- **Testing**: `docs/RUNBOOK_USER_AWARENESS.md`
- **Architecture**: `docs/USER_AWARENESS.md`
- **Examples**: `examples/memory_integration_example.py`

---

**Summary:** 
1. ✅ Deploy system first
2. ✅ Let it stabilize (48 hours)
3. ✅ THEN run backfill gradually
4. ✅ Set up automated backfill for maintenance

