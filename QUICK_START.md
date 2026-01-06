# Quick Start: User Awareness Memory System

Get up and running with the User Awareness system in 5 minutes.

## Prerequisites

- Python 3.10+
- MongoDB running
- Pinecone account
- OpenAI API key

## 1. Install Dependencies

```bash
pip install -r requirements.txt
```

## 2. Configure Environment

Create `.env` file:

```bash
# Copy template
cp env.example .env

# Edit .env and add:
OPENAI_API_KEY=sk-...
MONGO_URI=mongodb://localhost:27017/
PINECONE_API_KEY=your-key
PINECONE_INDEX_NAME=aivis-memory
PINECONE_ENV=us-east-1
```

## 3. Run Setup Script

```bash
python scripts/setup_memory_system.py
```

This will:
- ✅ Check environment variables
- ✅ Connect to MongoDB
- ✅ Create indexes
- ✅ Initialize Pinecone
- ✅ Test embeddings

## 4. Start Server

```bash
python server.py
```

Server starts on `http://localhost:10000`

## 5. Test the System

### Option A: Automated Test (Linux/Mac)

```bash
bash scripts/test_memory_system.sh
```

### Option B: Manual Test (All Platforms)

**Upload a document:**

```bash
# Create test file
echo "I am a software engineer who prefers morning meetings and async communication." > test.txt

# Upload
curl -X POST http://localhost:10000/memory/upload-file \
  -F "file=@test.txt" \
  -F "user_id=test-user" \
  -F "title=Test Document"
```

**Send a message:**

```bash
curl -X POST http://localhost:10000/memory/ingest-message \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user",
    "thread_id": "test-thread",
    "channel": "test",
    "direction": "in",
    "text": "I work at TechCorp and prefer async communication"
  }'
```

**Wait 5 seconds for background processing, then check facts:**

```bash
curl "http://localhost:10000/memory/facts?user_id=test-user"
```

**Retrieve context:**

```bash
curl "http://localhost:10000/memory/context?user_id=test-user&q=work"
```

## 6. Integrate into Your Code

### Simple Integration (One-Liner)

```python
from app.memory.prompt_builder import build_context_aware_messages
from app.services.llm_service import get_llm_service

# Build context-aware messages
messages = build_context_aware_messages(
    user_id="user123",
    thread_id="thread456",
    user_message="What are my preferences?",
)

# Generate response
llm = get_llm_service()
response = llm.call_llm(messages=messages)
```

### Full Example

```python
from app.memory.ingestion_service import get_ingestion_service
from app.memory.retrieval_service import get_retrieval_service
from app.memory.prompt_builder import PromptBuilder
from app.memory.models import MessageDirection

# 1. Ingest incoming message
ingestion = get_ingestion_service()
ingestion.ingest_message(
    user_id="user123",
    thread_id="thread456",
    channel="whatsapp",
    direction=MessageDirection.INCOMING,
    text="What's on my schedule today?",
    extract_facts=True,
)

# 2. Retrieve context
retrieval = get_retrieval_service()
bundle = retrieval.retrieve_context(
    user_id="user123",
    thread_id="thread456",
    query_text="What's on my schedule today?",
)

# 3. Build prompt
builder = PromptBuilder()
messages = builder.build_messages_with_context(
    bundle=bundle,
    user_message="What's on my schedule today?",
)

# 4. Generate response
llm = get_llm_service()
response = llm.call_llm(messages=messages)

# 5. Store response
ingestion.ingest_message(
    user_id="user123",
    thread_id="thread456",
    channel="whatsapp",
    direction=MessageDirection.OUTGOING,
    text=response,
)
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/memory/ingest-message` | POST | Ingest a message |
| `/memory/upload-file` | POST | Upload document |
| `/memory/context` | GET | Get context bundle |
| `/memory/facts` | GET | List facts |
| `/memory/facts` | POST | Add fact |
| `/memory/facts/<id>` | DELETE | Delete fact |
| `/memory/threads/<id>/summary` | GET | Get summary |
| `/memory/health` | GET | Health check |

## Common Issues

### Pinecone Not Connecting

```bash
# Check API key
echo $PINECONE_API_KEY

# Verify in Pinecone console that index exists
```

### Facts Not Being Extracted

```bash
# Check logs
tail -f logs/app.log | grep "fact"

# Add fact manually to test
curl -X POST http://localhost:10000/memory/facts \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user",
    "text": "User prefers morning meetings",
    "type": "preference",
    "confidence": 0.9
  }'
```

### Document Upload Fails

```bash
# Install document parsers
pip install PyPDF2 python-docx

# Create upload folder
mkdir -p uploads
```

## Next Steps

1. **Read the docs**: [docs/USER_AWARENESS.md](docs/USER_AWARENESS.md)
2. **Follow the runbook**: [docs/RUNBOOK_USER_AWARENESS.md](docs/RUNBOOK_USER_AWARENESS.md)
3. **Check examples**: [examples/memory_integration_example.py](examples/memory_integration_example.py)
4. **Run tests**: `pytest tests/test_memory_system.py -v`

## Architecture Overview

```
Message/File → Ingestion → Memory Gate → Storage (MongoDB + Pinecone)
                                              ↓
Query → Retrieval → Context Bundle → Prompt Builder → LLM → Response
```

## Key Features

- ✅ Automatic fact extraction from conversations
- ✅ Document upload and semantic search (RAG)
- ✅ Thread summarization for long-term memory
- ✅ User-isolated data (secure namespaces)
- ✅ Background processing (non-blocking)
- ✅ Token control (prevents cost explosion)

## Support

- **Full Documentation**: [docs/USER_AWARENESS.md](docs/USER_AWARENESS.md)
- **Testing Guide**: [docs/RUNBOOK_USER_AWARENESS.md](docs/RUNBOOK_USER_AWARENESS.md)
- **Code Examples**: [examples/](examples/)
- **Implementation Summary**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)

---

**Ready to go!** Start the server and begin testing. 🚀

