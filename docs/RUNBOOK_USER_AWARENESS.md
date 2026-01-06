# User Awareness Runbook

Quick start guide for testing the User Awareness memory system locally.

## Prerequisites

1. **Python 3.10+** installed
2. **MongoDB** running (local or Atlas)
3. **Pinecone account** with API key
4. **OpenAI API key**

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in:

```bash
# Required
OPENAI_API_KEY=sk-...
MONGO_URI=mongodb://localhost:27017/
PINECONE_API_KEY=your-pinecone-key
PINECONE_INDEX_NAME=aivis-memory
PINECONE_ENV=us-east-1

# Optional (for document processing)
UPLOAD_FOLDER=uploads
```

### 3. Create Upload Folder

```bash
mkdir -p uploads
```

### 4. Start Server

```bash
python server.py
```

Server will start on `http://localhost:10000`

## Testing Workflow

### Test 1: Upload a Document

Create a test document:

```bash
cat > test_doc.txt << 'EOF'
Project Overview: AI Assistant Development

Key Requirements:
- Natural language understanding
- Context awareness from past conversations
- Integration with email and calendar
- Document upload and RAG

Technical Stack:
- Backend: Python/Flask
- Database: MongoDB
- Vector DB: Pinecone
- LLM: OpenAI GPT-4

The assistant should remember user preferences and provide personalized responses.
EOF
```

Upload the document:

```bash
curl -X POST http://localhost:10000/memory/upload-file \
  -F "file=@test_doc.txt" \
  -F "user_id=test-user-123" \
  -F "title=Project Requirements"
```

Expected response:

```json
{
  "success": true,
  "doc_id": "doc-abc123...",
  "title": "Project Requirements",
  "indexed_at": "2024-01-06T10:00:00Z"
}
```

### Test 2: Send a Message (Extract Facts)

```bash
curl -X POST http://localhost:10000/memory/ingest-message \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-123",
    "thread_id": "test-thread-001",
    "channel": "test",
    "direction": "in",
    "text": "I prefer morning meetings and I work as a software engineer at TechCorp. I like async communication over phone calls."
  }'
```

Expected response:

```json
{
  "success": true,
  "message_id": "msg-xyz789...",
  "ingested_at": "2024-01-06T10:00:00Z"
}
```

**Wait 5-10 seconds** for background fact extraction to complete.

### Test 3: Verify Facts Were Extracted

```bash
curl "http://localhost:10000/memory/facts?user_id=test-user-123"
```

Expected response:

```json
{
  "success": true,
  "facts": [
    {
      "id": "fact-123",
      "text": "User prefers morning meetings",
      "type": "preference",
      "confidence": 0.9,
      "created_at": "2024-01-06T10:00:00Z"
    },
    {
      "id": "fact-456",
      "text": "User works as a software engineer at TechCorp",
      "type": "work",
      "confidence": 0.95,
      "created_at": "2024-01-06T10:00:00Z"
    },
    {
      "id": "fact-789",
      "text": "User prefers async communication over phone calls",
      "type": "preference",
      "confidence": 0.85,
      "created_at": "2024-01-06T10:00:00Z"
    }
  ],
  "count": 3
}
```

### Test 4: Retrieve Context (RAG)

Query with a question related to the uploaded document:

```bash
curl "http://localhost:10000/memory/context?user_id=test-user-123&q=project+requirements"
```

Expected response:

```json
{
  "success": true,
  "user_id": "test-user-123",
  "context": {
    "profile_summary": "Software engineer at TechCorp who prefers morning meetings",
    "facts": [
      {
        "text": "User works as a software engineer at TechCorp",
        "type": "work",
        "confidence": 0.95
      },
      {
        "text": "User prefers morning meetings",
        "type": "preference",
        "confidence": 0.9
      }
    ],
    "summaries": [],
    "doc_chunks": [
      {
        "text": "Project Overview: AI Assistant Development\n\nKey Requirements:\n- Natural language understanding\n- Context awareness from past conversations...",
        "doc_title": "Project Requirements",
        "chunk_index": 0,
        "score": 0.87
      }
    ],
    "recent_messages": [
      {
        "direction": "in",
        "text": "I prefer morning meetings and I work as a software engineer at TechCorp...",
        "ts": "2024-01-06T10:00:00Z"
      }
    ]
  },
  "stats": {
    "facts_count": 2,
    "summaries_count": 0,
    "doc_chunks_count": 1,
    "recent_messages_count": 1
  }
}
```

### Test 5: Send Multiple Messages (Thread Summary)

Send 5+ messages to trigger thread summarization:

```bash
for i in {1..6}; do
  curl -X POST http://localhost:10000/memory/ingest-message \
    -H "Content-Type: application/json" \
    -d "{
      \"user_id\": \"test-user-123\",
      \"thread_id\": \"test-thread-001\",
      \"channel\": \"test\",
      \"direction\": \"in\",
      \"text\": \"Message $i: This is a test message about the project.\"
    }"
  sleep 1
done
```

Check thread summary:

```bash
curl "http://localhost:10000/memory/threads/test-thread-001/summary?user_id=test-user-123"
```

Expected response:

```json
{
  "success": true,
  "thread_id": "test-thread-001",
  "summary": {
    "text": "User discussed their work preferences and sent multiple test messages about the project.",
    "updated_at": "2024-01-06T10:05:00Z",
    "message_count": 7,
    "window_start": "2024-01-06T10:00:00Z",
    "window_end": "2024-01-06T10:05:00Z"
  }
}
```

### Test 6: Search Facts

Search for specific facts:

```bash
# Search by keyword
curl "http://localhost:10000/memory/facts?user_id=test-user-123&q=meetings"

# Filter by type
curl "http://localhost:10000/memory/facts?user_id=test-user-123&type=preference"
```

### Test 7: Add Fact Manually

```bash
curl -X POST http://localhost:10000/memory/facts \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-123",
    "text": "User prefers written documentation over verbal explanations",
    "type": "preference",
    "confidence": 0.85
  }'
```

### Test 8: Delete a Fact

```bash
# First, get fact ID from list
FACT_ID=$(curl -s "http://localhost:10000/memory/facts?user_id=test-user-123" | jq -r '.facts[0].id')

# Delete it
curl -X DELETE "http://localhost:10000/memory/facts/$FACT_ID?user_id=test-user-123"
```

### Test 9: Health Check

```bash
curl http://localhost:10000/memory/health
```

Expected response:

```json
{
  "success": true,
  "status": "healthy",
  "components": {
    "database": "connected",
    "vector_store": "initialized"
  }
}
```

## Integration Example: Context-Aware Chat

Here's how to use the memory system in your chat endpoint:

```python
from app.memory.prompt_builder import build_context_aware_messages
from app.services.llm_service import get_llm_service

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_id = data['user_id']
    thread_id = data.get('thread_id', 'default')
    user_message = data['message']
    
    # Build context-aware messages
    messages = build_context_aware_messages(
        user_id=user_id,
        thread_id=thread_id,
        user_message=user_message,
    )
    
    # Generate response
    llm_service = get_llm_service()
    response = llm_service.call_llm(messages=messages)
    
    # Ingest the exchange
    from app.memory.ingestion_service import get_ingestion_service
    from app.memory.models import MessageDirection
    
    ingestion = get_ingestion_service()
    ingestion.ingest_message(
        user_id=user_id,
        thread_id=thread_id,
        channel='web_chat',
        direction=MessageDirection.INCOMING,
        text=user_message,
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

## Troubleshooting

### Issue: Facts not being extracted

**Check logs:**

```bash
# Look for "✅ Extracted N candidate facts"
tail -f logs/app.log | grep "fact"
```

**Verify LLM is working:**

```bash
curl -X POST http://localhost:10000/memory/facts \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-123",
    "text": "Manual test fact",
    "type": "other",
    "confidence": 0.9
  }'
```

### Issue: Pinecone connection failed

**Check environment:**

```bash
echo $PINECONE_API_KEY
echo $PINECONE_INDEX_NAME
```

**Verify index exists:**

Log in to Pinecone console and check that the index name matches.

**Create index manually if needed:**

```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="your-key")
pc.create_index(
    name="aivis-memory",
    dimension=1536,
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1")
)
```

### Issue: Document upload fails

**Check file type:**

Only `.txt`, `.pdf`, `.doc`, `.docx` are supported.

**Install document parsers:**

```bash
pip install PyPDF2 python-docx
```

**Check upload folder:**

```bash
mkdir -p uploads
chmod 755 uploads
```

### Issue: MongoDB not connected

**Check MongoDB is running:**

```bash
# Local MongoDB
mongosh

# Or check Atlas connection string
echo $MONGO_URI
```

## Running Unit Tests

```bash
# Install test dependencies
pip install pytest pytest-mock

# Run all tests
pytest tests/test_memory_system.py -v

# Run specific test
pytest tests/test_memory_system.py::TestMemoryGate::test_extract_candidate_facts -v
```

## Performance Monitoring

### Check Vector Store Stats

```python
from app.memory.vector_store import get_vector_store

store = get_vector_store()
stats = store.get_stats("test-user-123")
print(stats)
# {'total_vectors': 42, 'dimension': 1536}
```

### Check Token Usage

```python
from app.memory.retrieval_service import get_retrieval_service
from app.memory.prompt_builder import PromptBuilder

retrieval = get_retrieval_service()
bundle = retrieval.retrieve_context(
    user_id="test-user-123",
    query_text="project requirements"
)

builder = PromptBuilder()
token_count = builder.estimate_token_count(bundle)
print(f"Context uses ~{token_count} tokens")
```

## Next Steps

1. **Integrate with WhatsApp webhook**: Call `/memory/ingest-message` when messages arrive
2. **Add to chat endpoint**: Use `build_context_aware_messages()` for context injection
3. **Monitor costs**: Track token usage and adjust retrieval limits
4. **Tune parameters**: Adjust chunk size, retrieval limits, confidence thresholds
5. **Add user feedback**: Let users edit/confirm facts via UI

## Support

- Documentation: `docs/USER_AWARENESS.md`
- Code: `app/memory/`
- Tests: `tests/test_memory_system.py`

