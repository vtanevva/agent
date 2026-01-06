"""
Example: Integrating User Awareness into Chat Flow

This example shows how to use the memory system in your chat endpoints
to provide context-aware responses.
"""

from flask import Flask, request, jsonify
from app.memory.prompt_builder import build_context_aware_messages
from app.memory.ingestion_service import get_ingestion_service
from app.memory.models import MessageDirection
from app.services.llm_service import get_llm_service

app = Flask(__name__)


# ═══════════════════════════════════════════════════════════════════
# Example 1: Simple Context-Aware Chat
# ═══════════════════════════════════════════════════════════════════

@app.route('/chat/simple', methods=['POST'])
def chat_simple():
    """
    Simple chat endpoint with automatic context injection.
    
    The memory system will:
    1. Retrieve relevant facts about the user
    2. Get recent conversation history
    3. Search uploaded documents if query is relevant
    4. Build a context-aware prompt
    """
    data = request.json
    user_id = data['user_id']
    thread_id = data.get('thread_id', 'default')
    user_message = data['message']
    
    # Build context-aware messages (one-liner!)
    messages = build_context_aware_messages(
        user_id=user_id,
        thread_id=thread_id,
        user_message=user_message,
    )
    
    # Generate response
    llm_service = get_llm_service()
    response = llm_service.call_llm(messages=messages)
    
    # Store the conversation
    ingestion = get_ingestion_service()
    ingestion.ingest_message(
        user_id=user_id,
        thread_id=thread_id,
        channel='web_chat',
        direction=MessageDirection.INCOMING,
        text=user_message,
        extract_facts=True,  # Extract facts in background
    )
    ingestion.ingest_message(
        user_id=user_id,
        thread_id=thread_id,
        channel='web_chat',
        direction=MessageDirection.OUTGOING,
        text=response,
        extract_facts=False,  # Don't extract from bot responses
    )
    
    return jsonify({"response": response})


# ═══════════════════════════════════════════════════════════════════
# Example 2: Advanced Chat with Manual Context Control
# ═══════════════════════════════════════════════════════════════════

@app.route('/chat/advanced', methods=['POST'])
def chat_advanced():
    """
    Advanced chat with manual control over context retrieval.
    
    Use this when you want to:
    - Customize retrieval parameters
    - Access context components separately
    - Add custom context sources
    """
    from app.memory.retrieval_service import get_retrieval_service
    from app.memory.prompt_builder import PromptBuilder
    
    data = request.json
    user_id = data['user_id']
    thread_id = data.get('thread_id', 'default')
    user_message = data['message']
    
    # Step 1: Retrieve context
    retrieval = get_retrieval_service()
    bundle = retrieval.retrieve_context(
        user_id=user_id,
        thread_id=thread_id,
        query_text=user_message,
    )
    
    # Step 2: Optionally modify context
    # For example, filter facts by type
    bundle.top_facts = [
        f for f in bundle.top_facts
        if f.get('type') in ['preference', 'work']
    ]
    
    # Step 3: Build prompt
    builder = PromptBuilder()
    messages = builder.build_messages_with_context(
        bundle=bundle,
        user_message=user_message,
        include_recent_messages=True,
    )
    
    # Step 4: Generate response
    llm_service = get_llm_service()
    response = llm_service.call_llm(messages=messages)
    
    # Step 5: Store conversation
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
    
    return jsonify({
        "response": response,
        "context_stats": bundle.retrieval_stats,
    })


# ═══════════════════════════════════════════════════════════════════
# Example 3: WhatsApp Webhook Integration
# ═══════════════════════════════════════════════════════════════════

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """
    WhatsApp webhook that uses memory system.
    
    When a WhatsApp message arrives:
    1. Ingest the message (extracts facts automatically)
    2. Retrieve context
    3. Generate context-aware response
    4. Send response back to WhatsApp
    """
    data = request.json
    
    # Parse WhatsApp message
    from_number = data['from']
    message_text = data['text']
    
    # Map phone number to user_id (implement your own logic)
    user_id = f"whatsapp-{from_number}"
    thread_id = f"wa-{from_number}"
    
    # Ingest incoming message
    ingestion = get_ingestion_service()
    ingestion.ingest_message(
        user_id=user_id,
        thread_id=thread_id,
        channel='whatsapp',
        direction=MessageDirection.INCOMING,
        text=message_text,
        source_id=data.get('message_id'),
        extract_facts=True,
    )
    
    # Generate context-aware response
    messages = build_context_aware_messages(
        user_id=user_id,
        thread_id=thread_id,
        user_message=message_text,
    )
    
    llm_service = get_llm_service()
    response = llm_service.call_llm(messages=messages)
    
    # Store outgoing message
    ingestion.ingest_message(
        user_id=user_id,
        thread_id=thread_id,
        channel='whatsapp',
        direction=MessageDirection.OUTGOING,
        text=response,
    )
    
    # Send response via WhatsApp API (implement your own)
    # send_whatsapp_message(from_number, response)
    
    return jsonify({"status": "ok"})


# ═══════════════════════════════════════════════════════════════════
# Example 4: Email Draft with Context
# ═══════════════════════════════════════════════════════════════════

@app.route('/email/draft', methods=['POST'])
def draft_email_with_context():
    """
    Generate email draft using context from past conversations and documents.
    
    Example use case:
    - User: "Draft an email to John about the project requirements"
    - System retrieves: facts about John, project docs, past email threads
    - Generates: Personalized email draft
    """
    from app.memory.retrieval_service import get_retrieval_service
    from app.memory.prompt_builder import PromptBuilder
    
    data = request.json
    user_id = data['user_id']
    prompt = data['prompt']  # e.g., "Draft email to John about project"
    
    # Retrieve context
    retrieval = get_retrieval_service()
    bundle = retrieval.retrieve_context(
        user_id=user_id,
        query_text=prompt,
    )
    
    # Build specialized prompt for email drafting
    builder = PromptBuilder()
    system_prompt = builder.build_system_prompt(bundle, assistant_name="Aivis")
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{prompt}\n\nPlease draft a professional email."}
    ]
    
    # Generate draft
    llm_service = get_llm_service()
    draft = llm_service.call_llm(messages=messages)
    
    return jsonify({
        "draft": draft,
        "context_used": {
            "facts_count": len(bundle.top_facts),
            "doc_chunks_count": len(bundle.top_doc_chunks),
        }
    })


# ═══════════════════════════════════════════════════════════════════
# Example 5: Document Q&A
# ═══════════════════════════════════════════════════════════════════

@app.route('/documents/ask', methods=['POST'])
def ask_document():
    """
    Ask questions about uploaded documents.
    
    The system will:
    1. Search document chunks semantically
    2. Retrieve relevant excerpts
    3. Generate answer based on document content
    """
    from app.memory.retrieval_service import get_retrieval_service
    from app.memory.prompt_builder import PromptBuilder
    
    data = request.json
    user_id = data['user_id']
    question = data['question']
    
    # Retrieve context (focused on documents)
    retrieval = get_retrieval_service()
    bundle = retrieval.retrieve_context(
        user_id=user_id,
        query_text=question,
    )
    
    # Build prompt emphasizing document content
    builder = PromptBuilder()
    system_prompt = f"""You are Aivis, a document assistant.

Answer the user's question based ONLY on the provided document excerpts.
If the answer is not in the documents, say "I don't have that information in your documents."

DOCUMENT EXCERPTS:
"""
    
    for chunk in bundle.top_doc_chunks:
        system_prompt += f"\n[{chunk['doc_title']}]\n{chunk['text']}\n"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question}
    ]
    
    # Generate answer
    llm_service = get_llm_service()
    answer = llm_service.call_llm(messages=messages)
    
    # Include source citations
    sources = [
        {"title": c["doc_title"], "chunk": c["chunk_index"]}
        for c in bundle.top_doc_chunks
    ]
    
    return jsonify({
        "answer": answer,
        "sources": sources,
    })


# ═══════════════════════════════════════════════════════════════════
# Example 6: Batch Fact Extraction
# ═══════════════════════════════════════════════════════════════════

@app.route('/admin/extract-facts', methods=['POST'])
def batch_extract_facts():
    """
    Admin endpoint to batch extract facts from existing messages.
    
    Useful for:
    - Backfilling facts from old conversations
    - Re-processing after improving extraction logic
    """
    from app.memory.models import get_messages_collection
    from app.memory.memory_gate import get_memory_gate
    
    data = request.json
    user_id = data['user_id']
    limit = data.get('limit', 100)
    
    # Get recent messages
    messages_col = get_messages_collection()
    messages = list(messages_col.find(
        {"user_id": user_id, "direction": "in"},
        {"text": 1, "_id": 1}
    ).sort("ts", -1).limit(limit))
    
    # Extract facts from each
    gate = get_memory_gate()
    total_facts = 0
    
    for msg in messages:
        candidates = gate.extract_candidate_facts(
            text=msg["text"],
            user_id=user_id,
            source_ref=msg["_id"],
        )
        
        # Get existing facts for deduplication
        from app.memory.models import get_memory_facts_collection
        facts_col = get_memory_facts_collection()
        existing = list(facts_col.find(
            {"user_id": user_id, "is_active": True},
            {"text": 1}
        ))
        
        # Deduplicate and store
        unique = gate.deduplicate_facts(candidates, existing)
        count = gate.store_facts(user_id, unique)
        total_facts += count
    
    return jsonify({
        "messages_processed": len(messages),
        "facts_extracted": total_facts,
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)

