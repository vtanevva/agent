# Memory System Integration Examples

This directory contains examples showing how to integrate the User Awareness memory system into various parts of your application.

## Files

- `memory_integration_example.py` - Complete examples for different use cases

## Examples Included

### 1. Simple Context-Aware Chat

The easiest way to add memory to your chat:

```python
from backend.application.services.memory.prompt_builder import build_context_aware_messages

messages = build_context_aware_messages(
    user_id=user_id,
    thread_id=thread_id,
    user_message=user_message,
)

response = llm_service.call_llm(messages=messages)
```

### 2. Advanced Chat with Manual Control

For when you need more control over context retrieval:

```python
from backend.application.services.memory.retrieval_service import get_retrieval_service
from backend.application.services.memory.prompt_builder import PromptBuilder

retrieval_service = get_retrieval_service()
# Retrieve context
bundle = retrieval_service.retrieve_context(
    user_id=user_id,
    thread_id=thread_id,
    query_text=user_message,
)

# Customize context
bundle.top_facts = [f for f in bundle.top_facts if f['type'] == 'preference']

# Build prompt
builder = PromptBuilder()
messages = builder.build_messages_with_context(bundle, user_message)
```

### 3. WhatsApp Webhook

Integrate memory into WhatsApp message handling:

```python
# Ingest incoming message
ingestion.ingest_message(
    user_id=user_id,
    thread_id=thread_id,
    channel='whatsapp',
    direction=MessageDirection.INCOMING,
    text=message_text,
    extract_facts=True,  # Automatic fact extraction
)

# Generate context-aware response
messages = build_context_aware_messages(user_id, thread_id, message_text)
response = llm_service.call_llm(messages)
```

### 4. Email Draft Generation

Use context to draft personalized emails:

```python
# Retrieve context about recipient and topic
bundle = retrieval_service.retrieve_context(
    user_id=user_id,
    query_text="Draft email to John about project",
)

# Generate draft with context
messages = [
    {"role": "system", "content": builder.build_system_prompt(bundle)},
    {"role": "user", "content": "Draft email to John about project"}
]
draft = llm_service.call_llm(messages)
```

### 5. Document Q&A

Answer questions based on uploaded documents:

```python
# Retrieve relevant document chunks
bundle = retrieval_service.retrieve_context(
    user_id=user_id,
    query_text=question,
)

# Build prompt with document excerpts
system_prompt = "Answer based on these documents:\n"
for chunk in bundle.top_doc_chunks:
    system_prompt += f"[{chunk['doc_title']}]\n{chunk['text']}\n"

answer = llm_service.call_llm([
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": question}
])
```

### 6. Batch Fact Extraction

Backfill facts from existing conversations:

```python
# Get old messages
messages = messages_col.find({"user_id": user_id}).limit(100)

# Extract facts from each
gate = get_memory_gate()
for msg in messages:
    candidates = gate.extract_candidate_facts(msg["text"], user_id)
    gate.store_facts(user_id, candidates)
```

## Running Examples

```bash
# Run the example server
python examples/memory_integration_example.py

# Test simple chat
curl -X POST http://localhost:5000/chat/simple \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "message": "What are my preferences?"}'

# Test document Q&A
curl -X POST http://localhost:5000/documents/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "What are the project requirements?"}'
```

## Best Practices

1. **Always ingest messages**: Store both incoming and outgoing messages for full context
2. **Extract facts from user messages only**: Don't extract from bot responses
3. **Use thread IDs consistently**: Helps with conversation continuity
4. **Monitor token usage**: Use `PromptBuilder.estimate_token_count()` to check context size
5. **Handle errors gracefully**: Memory system failures shouldn't break your app

## Integration Checklist

- [ ] Add memory system imports to your chat endpoint
- [ ] Replace plain LLM calls with `build_context_aware_messages()`
- [ ] Ingest messages after each conversation turn
- [ ] Add document upload endpoint (or use `/memory/upload-file`)
- [ ] Test that facts are being extracted (check `/memory/facts`)
- [ ] Verify context is being retrieved (check `/memory/context`)
- [ ] Monitor token usage and costs
- [ ] Add error handling for memory system failures

## Troubleshooting

### Context not being retrieved

```python
# Debug: Check what context is available
from backend.application.services.memory.retrieval_service import get_retrieval_service

bundle = get_retrieval_service().retrieve_context(
    user_id="test-user",
    query_text="test query"
)

print(f"Facts: {len(bundle.top_facts)}")
print(f"Summaries: {len(bundle.top_summaries)}")
print(f"Doc chunks: {len(bundle.top_doc_chunks)}")
print(f"Messages: {len(bundle.recent_messages)}")
```

### Facts not being extracted

```python
# Debug: Manually extract facts
from backend.application.services.memory.memory_gate import get_memory_gate

gate = get_memory_gate()
candidates = gate.extract_candidate_facts(
    text="I prefer morning meetings",
    user_id="test-user"
)

print(f"Extracted {len(candidates)} facts")
for c in candidates:
    print(f"- {c.text} (confidence: {c.confidence})")
```

### High token usage

```python
# Check token count before calling LLM
from backend.application.services.memory.prompt_builder import PromptBuilder

builder = PromptBuilder()
token_count = builder.estimate_token_count(bundle)

if token_count > 2000:
    # Reduce context
    bundle.top_facts = bundle.top_facts[:5]
    bundle.top_doc_chunks = bundle.top_doc_chunks[:3]
```

## Next Steps

- Read [docs/USER_AWARENESS.md](../docs/USER_AWARENESS.md) for full documentation
- Follow [docs/RUNBOOK_USER_AWARENESS.md](../docs/RUNBOOK_USER_AWARENESS.md) for testing
- Check [tests/test_memory_system.py](../tests/test_memory_system.py) for unit tests

