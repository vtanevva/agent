"""
Memory API Routes

Endpoints for user awareness memory system:
- POST /memory/ingest-message - Ingest a message
- POST /memory/upload-file - Upload and index a document
- GET /memory/context - Get context bundle (debugging)
- GET /memory/facts - List user facts
- POST /memory/facts - Add/update a fact
- DELETE /memory/facts/<fact_id> - Delete a fact
- GET /threads/<thread_id>/summary - Get thread summary
"""

import logging
import os
from datetime import datetime
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from app.memory.ingestion_service import get_ingestion_service
from app.memory.retrieval_service import get_retrieval_service
from app.memory.memory_gate import get_memory_gate
from app.memory.models import (
    MessageDirection,
    DocumentSource,
    DocumentPermission,
    FactType,
    get_memory_facts_collection,
)
from app.utils.error_handler import handle_api_error

logger = logging.getLogger(__name__)

# Create blueprint
memory_bp = Blueprint('memory', __name__, url_prefix='/memory')

# Upload configuration
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@memory_bp.route('/ingest-message', methods=['POST'])
def ingest_message():
    """
    Ingest a message into memory system.
    
    Expected JSON body:
    {
        "user_id": "user123",
        "thread_id": "thread456",
        "channel": "whatsapp",
        "direction": "in",  // or "out"
        "text": "Message text",
        "ts": "2024-01-06T10:00:00Z",  // optional
        "source_id": "msg789",  // optional
        "meta": {}  // optional
    }
    """
    try:
        data = request.json
        
        # Validate required fields
        required = ['user_id', 'thread_id', 'channel', 'direction', 'text']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                "success": False,
                "error": f"Missing required fields: {', '.join(missing)}"
            }), 400
        
        # Parse timestamp
        ts = None
        if 'ts' in data:
            try:
                ts = datetime.fromisoformat(data['ts'].replace('Z', '+00:00'))
            except Exception:
                ts = None
        
        # Ingest message
        ingestion_service = get_ingestion_service()
        message_id = ingestion_service.ingest_message(
            user_id=data['user_id'],
            thread_id=data['thread_id'],
            channel=data['channel'],
            direction=MessageDirection(data['direction']),
            text=data['text'],
            ts=ts,
            source_id=data.get('source_id'),
            meta=data.get('meta'),
            extract_facts=True,
        )
        
        if message_id:
            return jsonify({
                "success": True,
                "message_id": message_id,
                "ingested_at": datetime.utcnow().isoformat()
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to ingest message"
            }), 500
            
    except Exception as e:
        logger.error(f"Error in ingest_message: {e}")
        return handle_api_error(e)


@memory_bp.route('/upload-file', methods=['POST'])
def upload_file():
    """
    Upload and index a document.
    
    Form data:
    - file: File to upload
    - user_id: User ID
    - title: Document title (optional, uses filename if not provided)
    - source: Document source (default: "upload")
    """
    try:
        # Check file in request
        if 'file' not in request.files:
            return jsonify({
                "success": False,
                "error": "No file provided"
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                "success": False,
                "error": "Empty filename"
            }), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                "success": False,
                "error": f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        # Get parameters
        user_id = request.form.get('user_id')
        if not user_id:
            return jsonify({
                "success": False,
                "error": "user_id required"
            }), 400
        
        title = request.form.get('title') or file.filename
        source = request.form.get('source', 'upload')
        
        # Save file
        filename = secure_filename(file.filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"{user_id}_{timestamp}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        file.save(filepath)
        logger.info(f"📁 Saved file: {filepath}")
        
        # Ingest document
        ingestion_service = get_ingestion_service()
        doc_id = ingestion_service.ingest_document(
            user_id=user_id,
            file_path=filepath,
            title=title,
            source=DocumentSource(source) if source in [s.value for s in DocumentSource] else DocumentSource.UPLOAD,
            permissions=DocumentPermission.PRIVATE,
        )
        
        if doc_id:
            return jsonify({
                "success": True,
                "doc_id": doc_id,
                "title": title,
                "indexed_at": datetime.utcnow().isoformat()
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to index document"
            }), 500
            
    except Exception as e:
        logger.error(f"Error in upload_file: {e}")
        return handle_api_error(e)


@memory_bp.route('/context', methods=['GET'])
def get_context():
    """
    Get context bundle for debugging.
    
    Query params:
    - user_id: User ID (required)
    - thread_id: Thread ID (optional)
    - q: Query text (optional)
    """
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({
                "success": False,
                "error": "user_id required"
            }), 400
        
        thread_id = request.args.get('thread_id')
        query = request.args.get('q')
        
        # Retrieve context
        retrieval_service = get_retrieval_service()
        bundle = retrieval_service.retrieve_context(
            user_id=user_id,
            thread_id=thread_id,
            query_text=query,
        )
        
        # Convert to JSON-serializable format
        return jsonify({
            "success": True,
            "user_id": bundle.user_id,
            "thread_id": bundle.thread_id,
            "context": {
                "profile_summary": bundle.profile_summary,
                "facts": bundle.top_facts,
                "summaries": bundle.top_summaries,
                "doc_chunks": bundle.top_doc_chunks,
                "recent_messages": [
                    {
                        "direction": msg.get("direction"),
                        "text": msg.get("text"),
                        "ts": msg.get("ts").isoformat() if msg.get("ts") else None
                    }
                    for msg in bundle.recent_messages
                ],
            },
            "stats": bundle.retrieval_stats,
        })
        
    except Exception as e:
        logger.error(f"Error in get_context: {e}")
        return handle_api_error(e)


@memory_bp.route('/facts', methods=['GET'])
def list_facts():
    """
    List user facts.
    
    Query params:
    - user_id: User ID (required)
    - q: Search query (optional)
    - type: Fact type filter (optional)
    - limit: Max results (default: 20)
    """
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({
                "success": False,
                "error": "user_id required"
            }), 400
        
        query = request.args.get('q')
        fact_type = request.args.get('type')
        limit = int(request.args.get('limit', 20))
        
        # Search facts
        retrieval_service = get_retrieval_service()
        facts = retrieval_service.search_facts(
            user_id=user_id,
            query=query,
            fact_type=fact_type,
            limit=limit,
        )
        
        # Convert to JSON format
        facts_json = []
        for fact in facts:
            facts_json.append({
                "id": str(fact.get("_id")),
                "text": fact.get("text"),
                "type": fact.get("type"),
                "confidence": fact.get("confidence"),
                "created_at": fact.get("created_at").isoformat() if fact.get("created_at") else None,
            })
        
        return jsonify({
            "success": True,
            "facts": facts_json,
            "count": len(facts_json),
        })
        
    except Exception as e:
        logger.error(f"Error in list_facts: {e}")
        return handle_api_error(e)


@memory_bp.route('/facts', methods=['POST'])
def add_fact():
    """
    Add or update a fact.
    
    Expected JSON body:
    {
        "user_id": "user123",
        "text": "User prefers morning meetings",
        "type": "preference",  // optional
        "confidence": 0.9  // optional
    }
    """
    try:
        data = request.json
        
        if not data.get('user_id') or not data.get('text'):
            return jsonify({
                "success": False,
                "error": "user_id and text required"
            }), 400
        
        from uuid import uuid4
        from app.memory.models import get_memory_facts_collection
        from app.memory.vector_store import get_vector_store
        
        facts_col = get_memory_facts_collection()
        if facts_col is None:
            return jsonify({
                "success": False,
                "error": "Database not available"
            }), 500
        
        # Create fact document
        fact_id = str(uuid4())
        fact_doc = {
            "_id": fact_id,
            "user_id": data['user_id'],
            "text": data['text'],
            "type": data.get('type', 'other'),
            "confidence": float(data.get('confidence', 0.8)),
            "source_ref": data.get('source_ref'),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
        }
        
        facts_col.insert_one(fact_doc)
        
        # Embed to vector store
        vector_store = get_vector_store()
        vector_store.upsert_vectors(
            user_id=data['user_id'],
            vectors=[{
                "id": fact_id,
                "text": data['text'],
                "metadata": {
                    "fact_type": fact_doc["type"],
                    "confidence": fact_doc["confidence"],
                }
            }],
            vector_type="fact"
        )
        
        logger.info(f"✅ Added fact: {data['text']}")
        
        return jsonify({
            "success": True,
            "fact_id": fact_id,
            "created_at": fact_doc["created_at"].isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in add_fact: {e}")
        return handle_api_error(e)


@memory_bp.route('/facts/<fact_id>', methods=['DELETE'])
def delete_fact(fact_id):
    """
    Delete (deactivate) a fact.
    
    Query params:
    - user_id: User ID (required, for security)
    """
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({
                "success": False,
                "error": "user_id required"
            }), 400
        
        from app.memory.models import get_memory_facts_collection
        
        facts_col = get_memory_facts_collection()
        if facts_col is None:
            return jsonify({
                "success": False,
                "error": "Database not available"
            }), 500
        
        # Deactivate fact (soft delete)
        result = facts_col.update_one(
            {"_id": fact_id, "user_id": user_id},
            {
                "$set": {
                    "is_active": False,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"🗑️ Deactivated fact: {fact_id}")
            return jsonify({
                "success": True,
                "fact_id": fact_id
            })
        else:
            return jsonify({
                "success": False,
                "error": "Fact not found or already deleted"
            }), 404
            
    except Exception as e:
        logger.error(f"Error in delete_fact: {e}")
        return handle_api_error(e)


@memory_bp.route('/threads/<thread_id>/summary', methods=['GET'])
def get_thread_summary(thread_id):
    """
    Get thread summary.
    
    Query params:
    - user_id: User ID (required)
    - force_update: Force regeneration (optional, default: false)
    """
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({
                "success": False,
                "error": "user_id required"
            }), 400
        
        force_update = request.args.get('force_update', '').lower() == 'true'
        
        from app.memory.models import get_thread_summaries_collection
        
        summaries_col = get_thread_summaries_collection()
        if summaries_col is None:
            return jsonify({
                "success": False,
                "error": "Database not available"
            }), 500
        
        # Force update if requested
        if force_update:
            ingestion_service = get_ingestion_service()
            ingestion_service.update_thread_summary(user_id, thread_id)
        
        # Get summary
        summary = summaries_col.find_one({
            "user_id": user_id,
            "thread_id": thread_id
        })
        
        if summary:
            return jsonify({
                "success": True,
                "thread_id": thread_id,
                "summary": {
                    "text": summary.get("summary_text"),
                    "updated_at": summary.get("updated_at").isoformat() if summary.get("updated_at") else None,
                    "message_count": summary.get("message_count"),
                    "window_start": summary.get("window_start_ts").isoformat() if summary.get("window_start_ts") else None,
                    "window_end": summary.get("window_end_ts").isoformat() if summary.get("window_end_ts") else None,
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "No summary found for this thread"
            }), 404
            
    except Exception as e:
        logger.error(f"Error in get_thread_summary: {e}")
        return handle_api_error(e)


@memory_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    from app.database import get_db
    from app.memory.vector_store import get_vector_store
    
    db = get_db()
    vector_store = get_vector_store()
    
    return jsonify({
        "success": True,
        "status": "healthy",
        "components": {
            "database": "connected" if db.is_connected else "disconnected",
            "vector_store": "initialized" if vector_store._initialized else "not_initialized",
        }
    })


@memory_bp.route('/admin/backfill-email-facts', methods=['POST'])
def backfill_email_facts():
    """
    Backfill facts from existing emails (ADMIN ONLY).
    
    Expected JSON body:
    {
        "user_id": "user123",  // required
        "max_emails": 100      // optional - default: 100
    }
    
    Returns:
    {
        "success": true,
        "message": "Backfill started",
        "user_id": "user123",
        "max_emails": 100
    }
    """
    try:
        data = request.json or {}
        
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({
                "success": False,
                "error": "user_id required"
            }), 400
        
        max_emails = int(data.get('max_emails', 100))
        
        # Trigger background classification (which now extracts facts)
        from app.services.gmail_service import classify_background
        import threading
        
        def run_backfill():
            try:
                result = classify_background(user_id, max_emails=max_emails)
                logger.info(f"Email fact backfill completed for user {user_id}: {result}")
            except Exception as e:
                logger.error(f"Email fact backfill failed for user {user_id}: {e}")
        
        # Run in background thread
        thread = threading.Thread(target=run_backfill, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "message": "Email fact backfill started in background",
            "user_id": user_id,
            "max_emails": max_emails,
            "note": "Check server logs for progress: '📧 Extracted X facts from email'"
        })
        
    except Exception as e:
        logger.error(f"Error starting email fact backfill: {e}")
        return handle_api_error(e)


@memory_bp.route('/admin/backfill-facts', methods=['POST'])
def backfill_facts():
    """
    Backfill facts from existing messages (ADMIN ONLY).
    
    Expected JSON body:
    {
        "user_id": "user123",  // optional - if not provided, processes all users
        "limit": 100,          // optional - messages per user (default: 100)
        "min_length": 20       // optional - minimum message length (default: 20)
    }
    """
    try:
        data = request.json or {}
        
        user_id = data.get('user_id')
        limit = int(data.get('limit', 100))
        min_length = int(data.get('min_length', 20))
        
        from app.memory.models import get_messages_collection, get_memory_facts_collection
        from app.memory.memory_gate import get_memory_gate
        from app.memory.vector_store import get_vector_store
        from uuid import uuid4
        
        messages_col = get_messages_collection()
        facts_col = get_memory_facts_collection()
        
        if not messages_col or not facts_col:
            return jsonify({
                "success": False,
                "error": "Database not available"
            }), 503
        
        # Get messages to process
        query = {"direction": "in"}
        if user_id:
            query["user_id"] = user_id
        
        messages = list(messages_col.find(
            query,
            {"text": 1, "_id": 1, "ts": 1, "user_id": 1}
        ).sort("ts", -1).limit(limit))
        
        if not messages:
            return jsonify({
                "success": True,
                "messages_processed": 0,
                "facts_extracted": 0,
                "message": "No messages found to process"
            })
        
        # Get existing facts for deduplication
        existing_query = {"is_active": True}
        if user_id:
            existing_query["user_id"] = user_id
        
        existing_facts = list(facts_col.find(existing_query, {"text": 1, "user_id": 1}))
        
        # Build existing facts map by user
        existing_by_user = {}
        for fact in existing_facts:
            uid = fact.get("user_id")
            if uid not in existing_by_user:
                existing_by_user[uid] = []
            existing_by_user[uid].append(fact)
        
        # Process messages
        gate = get_memory_gate()
        vector_store = get_vector_store()
        
        total_candidates = 0
        total_stored = 0
        processed = 0
        
        for msg in messages:
            text = msg.get("text", "").strip()
            msg_user_id = msg.get("user_id")
            
            if not msg_user_id or len(text) < min_length:
                continue
            
            processed += 1
            
            try:
                # Extract candidate facts
                candidates = gate.extract_candidate_facts(
                    text=text,
                    user_id=msg_user_id,
                    source_ref=msg["_id"],
                )
                
                if not candidates:
                    continue
                
                total_candidates += len(candidates)
                
                # Deduplicate against user's existing facts
                user_existing = existing_by_user.get(msg_user_id, [])
                unique = gate.deduplicate_facts(candidates, user_existing)
                
                if not unique:
                    continue
                
                # Store unique facts
                stored = gate.store_facts(msg_user_id, unique)
                total_stored += stored
                
                if stored > 0:
                    # Add to existing facts for next iteration
                    if msg_user_id not in existing_by_user:
                        existing_by_user[msg_user_id] = []
                    
                    for candidate in unique:
                        existing_by_user[msg_user_id].append({"text": candidate.text})
                    
                    # Embed facts to vector store
                    vectors = []
                    for candidate in unique:
                        vectors.append({
                            "id": f"fact-{uuid4().hex[:8]}",
                            "text": candidate.text,
                            "metadata": {
                                "fact_type": candidate.fact_type.value,
                                "confidence": candidate.confidence,
                            }
                        })
                    
                    if vectors:
                        vector_store.upsert_vectors(
                            user_id=msg_user_id,
                            vectors=vectors,
                            vector_type="fact"
                        )
                
            except Exception as e:
                logger.error(f"Error processing message {msg['_id']}: {e}")
                continue
        
        return jsonify({
            "success": True,
            "messages_processed": processed,
            "candidate_facts": total_candidates,
            "facts_stored": total_stored,
        })
        
    except Exception as e:
        logger.error(f"Error in backfill_facts: {e}")
        return handle_api_error(e)


# Export blueprint
__all__ = ['memory_bp']

