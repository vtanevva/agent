# User Awareness (Memory + Files)

## Overview

The User Awareness system enables Aivis to respond like a real assistant who knows the user's past messages, preferences, and uploaded documents. It implements a comprehensive memory and retrieval layer using:

- **MongoDB**: Stores messages, facts, thread summaries, and document metadata
- **Pinecone**: Vector database for semantic search over memories and documents
- **RAG (Retrieval Augmented Generation)**: Injects relevant context into prompts

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User Message / File                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Ingestion Service                           │
│  • Stores messages to MongoDB                                │
│  • Extracts text from documents (PDF/DOCX/TXT)              │
│  • Chunks documents for RAG                                  │
│  • Triggers fact extraction (async)                          │
│  • Updates thread summaries                                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Memory Gate                               │
│  • Extracts candidate facts from text                        │
│  • Validates facts (stable, not transient)                   │
│  • Deduplicates facts                                        │
│  • Stores to MongoDB + embeds to Pinecone                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Vector Store (Pinecone)                         │
│  • Namespaces per user_id (data isolation)                   │
│  • Types: fact, summary, doc_chunk, message                  │
│  • Semantic search for context retrieval                     │
└─────────────────────────────────────────────────────────────┘

                    ┌───────────────┐
                    │ User Query    │
                    └───────┬───────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 Retrieval Service                            │
│  • Profile summary (from facts)                              │
│  • Top facts (semantic search)                               │
│  • Thread summaries (past context)                           │
│  • Document chunks (RAG)                                     │
│  • Recent messages (conversation continuity)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Prompt Builder                              │
│  • Injects context into system prompt                        │
│  • Formats for OpenAI messages API                           │
│  • Token budget control                                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                      LLM                                     │
│  Generates context-aware response                            │
└─────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Data Models (`app/memory/models.py`)

**MongoDB Collections:**

- `users`: User profiles
- `messages`: All messages (chat, email, WhatsApp, etc.)
- `memory_facts`: Curated facts about users
- `thread_summaries`: Rolling summaries of conversation threads
- `documents`: Document metadata
- `document_chunks`: Text chunks for RAG

### 2. Vector Store (`app/memory/vector_store.py`)

- Pinecone interface with user-isolated namespaces
- Vector types: `fact`, `summary`, `doc_chunk`, `message`
- Metadata filtering for secure retrieval

### 3. Ingestion Service (`app/memory/ingestion_service.py`)

- `ingest_message()`: Store messages, extract facts, update summaries
- `ingest_document()`: Extract text, chunk, embed
- Background processing for non-blocking operations

### 4. Memory Gate (`app/memory/memory_gate.py`)

- Extracts stable facts (preferences, identity, work)
- Rejects transient statements ("I'm feeling sad today")
- Deduplicates using semantic similarity

### 5. Retrieval Service (`app/memory/retrieval_service.py`)

- `retrieve_context()`: Returns ContextBundle with all relevant context
- Hybrid ranking: semantic similarity + recency
- Hard limits for token control

### 6. Prompt Builder (`app/memory/prompt_builder.py`)

- Builds system prompts with injected context
- Formats for OpenAI messages API
- Token estimation

## Environment Variables

Add these to your `.env` file:

```bash
# Vector Database (Pinecone)
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_INDEX_NAME=aivis-memory
PINECONE_ENV=us-east-1

# OpenAI (for embeddings and LLM)
OPENAI_API_KEY=your-openai-api-key
EMBEDDING_MODEL=text-embedding-ada-002

# MongoDB (already configured)
MONGO_URI=your-mongodb-uri
MONGO_DB_NAME=productivity-assistant

# Upload folder for documents
UPLOAD_FOLDER=uploads
```

## API Endpoints

### 1. Ingest Message

```bash
POST /memory/ingest-message
Content-Type: application/json

{
  "user_id": "user123",
  "thread_id": "thread456",
  "channel": "whatsapp",
  "direction": "in",
  "text": "I prefer morning meetings and I work at TechCorp",
  "ts": "2024-01-06T10:00:00Z"
}
```

### 2. Upload File

```bash
POST /memory/upload-file
Content-Type: multipart/form-data

file: <file>
user_id: user123
title: Project Requirements
```

### 3. Get Context (Debug)

```bash
GET /memory/context?user_id=user123&thread_id=thread456&q=meetings

Response:
{
  "success": true,
  "context": {
    "profile_summary": "Software engineer at TechCorp",
    "facts": [...],
    "summaries": [...],
    "doc_chunks": [...],
    "recent_messages": [...]
  },
  "stats": {
    "facts_count": 5,
    "summaries_count": 2,
    "doc_chunks_count": 3,
    "recent_messages_count": 10
  }
}
```

### 4. List Facts

```bash
GET /memory/facts?user_id=user123&q=meetings&type=preference

Response:
{
  "success": true,
  "facts": [
    {
      "id": "fact-123",
      "text": "User prefers morning meetings",
      "type": "preference",
      "confidence": 0.9,
      "created_at": "2024-01-06T10:00:00Z"
    }
  ]
}
```

### 5. Add Fact

```bash
POST /memory/facts
Content-Type: application/json

{
  "user_id": "user123",
  "text": "User prefers email over phone calls",
  "type": "preference",
  "confidence": 0.9
}
```

### 6. Delete Fact

```bash
DELETE /memory/facts/fact-123?user_id=user123
```

### 7. Get Thread Summary

```bash
GET /memory/threads/thread456/summary?user_id=user123&force_update=false

Response:
{
  "success": true,
  "thread_id": "thread456",
  "summary": {
    "text": "User discussed project requirements and scheduled a meeting for next week.",
    "updated_at": "2024-01-06T10:00:00Z",
    "message_count": 15
  }
}
```

## Usage Examples

### Example 1: Upload a Document

```bash
# Upload a PDF document
curl -X POST http://localhost:10000/memory/upload-file \
  -F "file=@project_requirements.pdf" \
  -F "user_id=user123" \
  -F "title=Project Requirements"

# Response
{
  "success": true,
  "doc_id": "doc-abc123",
  "title": "Project Requirements",
  "indexed_at": "2024-01-06T10:00:00Z"
}
```

### Example 2: Verify Document is Indexed

```bash
# Query context with document-related question
curl "http://localhost:10000/memory/context?user_id=user123&q=project+requirements"

# Response will include doc_chunks
{
  "context": {
    "doc_chunks": [
      {
        "text": "The project requires building an AI assistant...",
        "doc_title": "Project Requirements",
        "chunk_index": 0,
        "score": 0.85
      }
    ]
  }
}
```

### Example 3: Send WhatsApp Message with Context

```python
from app.memory.prompt_builder import build_context_aware_messages
from app.services.llm_service import get_llm_service

# When WhatsApp message arrives
user_id = "user123"
thread_id = "whatsapp-thread-456"
user_message = "What are the project requirements?"

# Build context-aware prompt
messages = build_context_aware_messages(
    user_id=user_id,
    thread_id=thread_id,
    user_message=user_message,
)

# Generate response with context
llm_service = get_llm_service()
response = llm_service.call_llm(messages=messages)

print(response)
# "Based on your uploaded document, the project requires building 
#  an AI assistant with natural language understanding, context 
#  awareness, and email/calendar integration..."
```

### Example 4: Programmatic Usage

```python
from app.memory.ingestion_service import get_ingestion_service
from app.memory.retrieval_service import get_retrieval_service
from app.memory.models import MessageDirection

# Ingest a message
ingestion = get_ingestion_service()
message_id = ingestion.ingest_message(
    user_id="user123",
    thread_id="thread456",
    channel="email",
    direction=MessageDirection.INCOMING,
    text="I prefer morning meetings and work at TechCorp",
    extract_facts=True,  # Will extract facts in background
)

# Retrieve context
retrieval = get_retrieval_service()
bundle = retrieval.retrieve_context(
    user_id="user123",
    thread_id="thread456",
    query_text="What are my preferences?",
)

print(bundle.profile_summary)
# "Software engineer at TechCorp who prefers morning meetings"

print(bundle.top_facts)
# [{"text": "User prefers morning meetings", "type": "preference", ...}]
```

## Testing Locally

### 1. Set Up Environment

```bash
# Install dependencies
pip install -r requirements.txt

# Add to .env
PINECONE_API_KEY=your-key
PINECONE_INDEX_NAME=aivis-memory
OPENAI_API_KEY=your-key
```

### 2. Start Server

```bash
python server.py
```

### 3. Test File Upload

```bash
# Create a test file
echo "I am a software engineer who prefers morning meetings." > test.txt

# Upload
curl -X POST http://localhost:10000/memory/upload-file \
  -F "file=@test.txt" \
  -F "user_id=test-user" \
  -F "title=Test Document"
```

### 4. Test Message Ingestion

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

### 5. Test Context Retrieval

```bash
# Wait a few seconds for background processing, then:
curl "http://localhost:10000/memory/context?user_id=test-user&q=work"

# Should return facts about TechCorp and preferences
```

### 6. Run Unit Tests

```bash
pytest tests/test_memory_system.py -v
```

## Security & Privacy

### User Isolation

- **Pinecone namespaces**: Each user has a separate namespace
- **MongoDB queries**: Always filtered by `user_id`
- **API endpoints**: Require `user_id` parameter for all operations

### Fact Curation

- Only stable, long-term facts are stored
- Transient emotions and one-off events are filtered out
- Confidence threshold (>0.5) for storage

### Data Retention

- Facts can be deleted via API
- Soft delete (sets `is_active=false`)
- Vector embeddings can be removed from Pinecone

## Performance & Costs

### Token Control

- Hard limits on retrieved items:
  - Max 10 facts
  - Max 5 summaries
  - Max 8 doc chunks
  - Max 20 recent messages
- Estimated token count before LLM call

### Background Processing

- Fact extraction: async (doesn't block webhook)
- Thread summarization: triggered every 5 messages
- Document indexing: async

### Optimization Tips

1. **Adjust chunk size**: Smaller chunks = more granular but more vectors
2. **Tune retrieval limits**: Fewer items = lower token cost
3. **Use thread summaries**: More efficient than full message history
4. **Filter by fact type**: Only retrieve relevant fact types

## Troubleshooting

### Pinecone Not Connecting

```bash
# Check API key
echo $PINECONE_API_KEY

# Check index exists
# Log in to Pinecone console and verify index name
```

### Facts Not Being Extracted

```bash
# Check logs for fact extraction
# Look for "✅ Extracted N candidate facts"

# Test manually
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
# Check file type is supported (txt, pdf, docx)
# Check UPLOAD_FOLDER exists and is writable
mkdir -p uploads
chmod 755 uploads

# For PDF support, install PyPDF2
pip install PyPDF2

# For DOCX support, install python-docx
pip install python-docx
```

## Future Enhancements

- [ ] Replace thread-based background jobs with Celery/RQ
- [ ] Add support for more document types (Markdown, HTML)
- [ ] Implement fact confidence decay over time
- [ ] Add user feedback loop for fact validation
- [ ] Support for shared/team knowledge bases
- [ ] Integration with Google Drive and Notion
- [ ] Semantic deduplication using vector similarity

## Support

For issues or questions, see:
- Main README: `README.md`
- System Architecture: `SYSTEM_ARCHITECTURE.md`
- Code: `app/memory/`

