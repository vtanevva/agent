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
    get_tasks_collection,
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


@memory_bp.route('/email-processing-status', methods=['GET'])
def email_processing_status():
    """
    Get email classification status for a user.
    
    Query params:
    - user_id: User ID (required)
    
    Returns:
    {
        "success": true,
        "user_id": "v",
        "email_count": 150,
        "classified_count": 120,
        "status": "completed",  // "not_started", "in_progress", "completed"
        "started_at": "2026-01-06T...",
        "completed_at": "2026-01-06T...",
        "message": "All emails classified"
    }
    """
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({
                "success": False,
                "error": "user_id required"
            }), 400
        
        from app.database import get_db
        from app.tools.email.classifier import CLASSIFICATION_VERSION
        
        db = get_db()
        if not db.is_connected or db.db is None:
            return jsonify({
                "success": False,
                "error": "Database not connected"
            }), 500
        
        users_col = db.db["users"]
        emails_col = db.db["emails"]
        
        # Get user document
        user_doc = users_col.find_one({"user_id": user_id})
        
        # Count total emails and classified emails
        email_count = emails_col.count_documents({"user_id": user_id})
        classified_count = emails_col.count_documents({
            "user_id": user_id,
            "classification_version": CLASSIFICATION_VERSION
        })
        
        # Determine status
        if email_count == 0:
            status = "no_emails"
            message = "No emails to classify"
        elif not user_doc or not user_doc.get("initial_email_classification_done"):
            if classified_count > 0:
                status = "in_progress"
                message = f"Classifying emails... ({classified_count}/{email_count} done)"
            else:
                status = "not_started"
                message = f"{email_count} emails waiting to be classified"
        else:
            status = "completed"
            message = f"All {email_count} emails classified (v{CLASSIFICATION_VERSION})"
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "email_count": email_count,
            "classified_count": classified_count,
            "status": status,
            "classification_version": CLASSIFICATION_VERSION,
            "started_at": user_doc.get("email_classification_started_at") if user_doc else None,
            "completed_at": user_doc.get("email_classification_completed_at") if user_doc else None,
            "message": message
        })
        
    except Exception as e:
        logger.error(f"Error checking email processing status: {e}")
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


@memory_bp.route('/admin/backfill-comprehensive', methods=['POST'])
def backfill_comprehensive():
    """
    Comprehensive backfill: Extract facts, tasks, relationships, and projects from past emails.
    Note: Only processes emails. Chat messages are processed on-the-fly as they arrive (no backfill needed).
    
    Expected JSON body:
    {
        "user_id": "user123",  // required
        "max_emails": 20      // optional - default: 20
    }
    
    Returns:
    {
        "success": true,
        "message": "Comprehensive backfill started",
        "user_id": "user123"
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
        
        max_emails = int(data.get('max_emails', 20))
        
        from app.services.gmail_service import extract_facts_from_email, extract_todos_from_thread
        from app.tools.email import _extract_plain_text
        from app.utils.oauth_utils import load_google_credentials
        from googleapiclient.discovery import build
        import threading
        import time
        
        def run_comprehensive_backfill():
            try:
                # Get initial counts to calculate deltas
                from app.memory.models import (
                    get_memory_facts_collection, 
                    get_relationships_collection, 
                    get_projects_collection,
                    get_project_contact_relationships_collection
                )
                facts_col = get_memory_facts_collection()
                relationships_col = get_relationships_collection()  # Old collection
                project_relationships_col = get_project_contact_relationships_collection()  # New collection
                projects_col = get_projects_collection()
                
                initial_facts_count = facts_col.count_documents({"user_id": user_id}) if facts_col is not None else 0
                initial_relationships_count = relationships_col.count_documents({"user_id": user_id}) if relationships_col is not None else 0
                initial_project_relationships_count = project_relationships_col.count_documents({"user_id": user_id}) if project_relationships_col is not None else 0
                initial_projects_count = projects_col.count_documents({"user_id": user_id}) if projects_col is not None else 0
                
                stats = {
                    "emails_processed": 0,
                    "emails_skipped": 0,  # Newsletter/marketing emails skipped
                    "facts_extracted": 0,
                    "tasks_extracted": 0,
                    "relationships_updated": 0,  # Old collection
                    "project_relationships_created": 0,  # New collection
                    "projects_created": 0,
                    "skipped_categories": {}  # Track which categories were skipped
                }
                
                # ===== 1. BACKFILL FROM EMAILS =====
                logger.info(f"[BACKFILL] Starting comprehensive backfill for user {user_id}")
                
                # Load credentials and build Gmail service
                creds = load_google_credentials(user_id)
                if creds:
                    try:
                        service = build("gmail", "v1", credentials=creds)
                        
                        # Fetch recent emails from inbox (both received and sent)
                        logger.info(f"[BACKFILL] Fetching up to {max_emails} emails (user: {user_id})")
                        resp = service.users().messages().list(
                            userId="me",
                            q="in:inbox OR in:sent",  # Include both received and sent emails
                            maxResults=max_emails,  # Fetch same as process limit
                        ).execute()
                        
                        messages = resp.get("messages", []) or []
                        seen_threads = set()
                        processed = 0
                        
                        # Process emails to extract facts, relationships, projects, and tasks
                        for msg_info in messages:
                            if processed >= max_emails:
                                break
                            
                            try:
                                msg_id = msg_info["id"]
                                
                                # Fetch full message
                                full_msg = service.users().messages().get(
                                    userId="me",
                                    id=msg_id,
                                    format="full",
                                ).execute()
                                
                                thread_id = full_msg.get("threadId")
                                if thread_id in seen_threads:
                                    continue  # Skip duplicate threads
                                seen_threads.add(thread_id)
                                
                                # Extract email data
                                headers = {h["name"]: h["value"] for h in full_msg.get("payload", {}).get("headers", [])}
                                payload = full_msg.get("payload", {})
                                body = _extract_plain_text(payload)
                                
                                email_data = {
                                    "thread_id": thread_id,
                                    "from": headers.get("From", ""),
                                    "to": headers.get("To", ""),  # Add To field for relationship tracking
                                    "subject": headers.get("Subject", "(No subject)"),
                                    "snippet": full_msg.get("snippet", "")[:200],
                                    "body": body[:2000],  # Limit body length
                                }
                                
                                # CLASSIFICATION: Filter out newsletters, marketing, and noise emails
                                # Only extract facts from important emails
                                from app.tools.email.classifier import classify_email
                                
                                try:
                                    classification = classify_email(email_data, user_id)
                                    category = classification.get("category", "normal")
                                    
                                    # Skip fact extraction for noise categories
                                    skip_categories = [
                                        "newsletters",
                                        "promotional", 
                                        "social",
                                        "transactional"
                                    ]
                                    
                                    if category in skip_categories:
                                        logger.info(f"[BACKFILL] Skipping {category} email: {email_data.get('subject', '')[:50]}")
                                        stats["emails_skipped"] += 1  # Count skipped emails
                                        stats["skipped_categories"][category] = stats["skipped_categories"].get(category, 0) + 1
                                        continue
                                    
                                    # Add category to email_data for reference
                                    email_data["category"] = category
                                    logger.debug(f"[BACKFILL] Processing {category} email: {email_data.get('subject', '')[:50]}")
                                    
                                except Exception as e:
                                    logger.warning(f"[BACKFILL] Classification failed for thread {thread_id}, processing anyway: {e}")
                                    # Continue processing even if classification fails
                                    email_data["category"] = "unknown"
                                
                                # Extract facts (runs in background thread)
                                extract_facts_from_email(user_id, email_data)
                                
                                # Extract relationships and projects synchronously for accurate stats
                                try:
                                    from app.services.relationships_service import get_relationships_service
                                    from app.agents.contacts_agent import ContactsAgent
                                    
                                    relationships_service = get_relationships_service()
                                    contacts_agent = ContactsAgent()
                                    
                                    relationship_result = relationships_service.process_email(user_id, email_data)
                                    tracked_emails = relationship_result.get("tracked_emails", [])
                                    
                                    # Extract sender/recipient emails directly from email_data for project-contact relationships
                                    # Only include contacts with bidirectional communication (both sent and received)
                                    potential_contacts = set()
                                    
                                    # Log email data for debugging
                                    sender = email_data.get('from', '')
                                    recipients = email_data.get('to', '')
                                    email_sent_by_user = relationship_result.get("email_sent_by_user", False)
                                    
                                    logger.debug(f"[BACKFILL] Email data - from: '{sender}', to: '{recipients}', sent_by_user: {email_sent_by_user}, tracked: {tracked_emails}")
                                    
                                    # Extract sender email (for received emails)
                                    if sender and not email_sent_by_user:
                                        sender_email = relationships_service._extract_email_from_string(sender)
                                        if sender_email:
                                            is_user_email = relationships_service._is_email_from_user(user_id, sender_email)
                                            if not is_user_email:
                                                potential_contacts.add(('received', sender_email))
                                                logger.debug(f"[BACKFILL] Received email from: {sender_email}")
                                    
                                    # Extract recipient emails (for sent emails)
                                    if recipients and email_sent_by_user:
                                        if isinstance(recipients, str):
                                            recipient_list = [recipients]
                                        elif isinstance(recipients, list):
                                            recipient_list = recipients
                                        else:
                                            recipient_list = []
                                        
                                        for recipient in recipient_list:
                                            recipient_email = relationships_service._extract_email_from_string(recipient)
                                            if recipient_email:
                                                is_user_email = relationships_service._is_email_from_user(user_id, recipient_email)
                                                if not is_user_email:
                                                    potential_contacts.add(('sent', recipient_email))
                                                    logger.debug(f"[BACKFILL] Sent email to: {recipient_email}")
                                    
                                    # Check for bidirectional communication
                                    # Only include contacts where user has both sent AND received emails
                                    from app.memory.models import get_relationships_collection
                                    old_relationships_col = get_relationships_collection()
                                    
                                    all_contact_emails = []
                                    
                                    # Group potential contacts by email and direction
                                    contact_sent = set()  # Emails we sent to
                                    contact_received = set()  # Emails we received from
                                    
                                    for direction, email in potential_contacts:
                                        if direction == 'sent':
                                            contact_sent.add(email)
                                        elif direction == 'received':
                                            contact_received.add(email)
                                    
                                    # Check each potential contact for bidirectional communication
                                    # Use old relationships collection which tracks both sent and received interactions
                                    if old_relationships_col is not None:
                                        # First, check if any contacts were just tracked (meaning relationship was created/updated)
                                        tracked_emails_lower = {e.lower() for e in tracked_emails}
                                        
                                        for contact_email in contact_sent | contact_received:
                                            contact_email_lower = contact_email.lower()
                                            
                                            # If this contact was just tracked, it means we have a relationship
                                            if contact_email_lower in tracked_emails_lower:
                                                # Relationship was just created/updated - check if it has contact_count > 0
                                                relationship = old_relationships_col.find_one({
                                                    "user_id": user_id,
                                                    "contact_email": contact_email_lower
                                                })
                                                
                                                if relationship:
                                                    contact_count = relationship.get("contact_count", 0)
                                                    if contact_count > 0:
                                                        all_contact_emails.append(contact_email)
                                                        logger.info(f"[BACKFILL] Bidirectional contact confirmed (just tracked): {contact_email} (interactions: {contact_count})")
                                                    else:
                                                        logger.debug(f"[BACKFILL] Skipping contact with no interaction count: {contact_email}")
                                                else:
                                                    logger.debug(f"[BACKFILL] Contact was tracked but relationship not found in DB: {contact_email}")
                                            else:
                                                # Check if relationship exists from previous interactions
                                                relationship = old_relationships_col.find_one({
                                                    "user_id": user_id,
                                                    "contact_email": contact_email_lower
                                                })
                                                
                                                if relationship:
                                                    # Relationship exists - this means we've had bidirectional communication
                                                    # (relationships are only created/updated when there's real email exchange)
                                                    contact_count = relationship.get("contact_count", 0)
                                                    if contact_count > 0:
                                                        all_contact_emails.append(contact_email)
                                                        logger.info(f"[BACKFILL] Bidirectional contact confirmed (existing relationship): {contact_email} (interactions: {contact_count})")
                                                    else:
                                                        logger.debug(f"[BACKFILL] Skipping contact with no interaction count: {contact_email}")
                                                else:
                                                    # No relationship exists yet - skip this contact
                                                    # We only want contacts with real bidirectional communication
                                                    logger.debug(f"[BACKFILL] Skipping contact without existing relationship (no bidirectional communication yet): {contact_email}")
                                    else:
                                        # Fallback: if relationships collection not available, 
                                        # only include if contact appears in both sent and received in current batch
                                        # (This is a weaker check but better than nothing)
                                        all_contact_emails = list(contact_sent & contact_received)
                                        if all_contact_emails:
                                            logger.warning(f"[BACKFILL] Relationships collection not available, using fallback: {all_contact_emails}")
                                        else:
                                            logger.warning(f"[BACKFILL] Relationships collection not available and no bidirectional contacts in current batch")
                                    
                                    logger.info(f"[BACKFILL] Bidirectional contacts extracted: {all_contact_emails} (from potential: {len(potential_contacts)}, thread: {thread_id})")
                                    
                                    # Count if new relationships were tracked (old collection)
                                    if tracked_emails:
                                        # Relationship was created or updated (we'll count at the end by comparing counts)
                                        pass
                                    
                                    # Process projects synchronously
                                    from app.memory.models import get_projects_collection
                                    from uuid import uuid4
                                    projects_col = get_projects_collection()
                                    
                                    project_name = None
                                    if projects_col is not None and thread_id:
                                        subject = email_data.get('subject', '')
                                        # Check if thread already linked to project
                                        existing_project = projects_col.find_one({
                                            "user_id": user_id,
                                            "related_threads": thread_id
                                        })
                                        
                                        if existing_project:
                                            # Project already exists for this thread - use it
                                            project_name = existing_project.get("name")
                                            logger.info(f"[BACKFILL] Found existing project '{project_name}' for thread {thread_id}")
                                        else:
                                            logger.debug(f"[BACKFILL] No existing project found for thread {thread_id}")
                                            # Check if subject suggests a project
                                            # Check if subject suggests a project
                                            project_keywords = ["project", "launch", "initiative", "campaign", "feature", "release", "sprint", "milestone"]
                                            subject_lower = subject.lower()
                                            
                                            if any(keyword in subject_lower for keyword in project_keywords):
                                                project_name = subject[:100]
                                                
                                                result = projects_col.update_one(
                                                    {
                                                        "user_id": user_id,
                                                        "name": project_name
                                                    },
                                                    {
                                                        "$addToSet": {"related_threads": thread_id},
                                                        "$set": {
                                                            "last_activity": datetime.utcnow(),
                                                            "updated_at": datetime.utcnow()
                                                        },
                                                        "$setOnInsert": {
                                                            "_id": str(uuid4()),
                                                            "user_id": user_id,
                                                            "name": project_name,
                                                            "status": "active",
                                                            "created_at": datetime.utcnow()
                                                        }
                                                    },
                                                    upsert=True
                                                )
                                                stats["projects_created"] += 1
                                                
                                                # Link recipient(s) to project if we have relationships (old collection)
                                                if tracked_emails:
                                                    for recipient_email in tracked_emails:
                                                        relationships_service.link_project(user_id, recipient_email, project_name)
                                    # Note: project_name is already set above if existing_project was found
                                    if not project_name:
                                        # Check if project already exists (might be created in a previous email)
                                        if projects_col is not None and thread_id:
                                            existing = projects_col.find_one({
                                                "user_id": user_id,
                                                "related_threads": thread_id
                                            })
                                            if existing:
                                                project_name = existing.get("name")
                                                logger.debug(f"[BACKFILL] Found existing project '{project_name}' for thread {thread_id} (fallback check)")
                                    
                                    # Create relationships in NEW collection (project_contact_relationships)
                                    # Create relationships even if we have contacts OR projects (or both)
                                    if all_contact_emails or project_name:
                                        try:
                                            # Use msg_id from the loop scope, or thread_id as fallback
                                            source_message_id = f"{thread_id}_{msg_id}" if msg_id else thread_id
                                            
                                            # Log what we're about to create
                                            logger.debug(f"[BACKFILL] Creating relationship: project_name='{project_name}', contacts={all_contact_emails}, thread={thread_id}")
                                            
                                            # Create relationship in new collection
                                            rel_result = contacts_agent.create_or_update_relationship(
                                                user_id=user_id,
                                                projects=[project_name] if project_name else None,
                                                contacts=all_contact_emails if all_contact_emails else None,
                                                source_message_id=source_message_id,
                                                source="email",
                                            )
                                            if rel_result:
                                                logger.info(f"[BACKFILL] Created/updated relationship: projects={[project_name] if project_name else []}, contacts={all_contact_emails}, thread_id={thread_id}")
                                            else:
                                                logger.warning(f"[BACKFILL] Failed to create relationship: projects={[project_name] if project_name else []}, contacts={all_contact_emails}")
                                        except Exception as e:
                                            logger.warning(f"[BACKFILL] Failed to create relationship in new collection: {e}")
                                    
                                except Exception as e:
                                    logger.warning(f"Relationship/project extraction failed for thread {thread_id}: {e}")
                                
                                stats["emails_processed"] += 1
                                
                                # Extract tasks from thread (separate call)
                                try:
                                    todos_result = extract_todos_from_thread(user_id, thread_id)
                                    if todos_result.get("success") and todos_result.get("tasks_stored", 0) > 0:
                                        stats["tasks_extracted"] += todos_result.get("tasks_stored", 0)
                                except Exception as e:
                                    logger.warning(f"Task extraction failed for thread {thread_id}: {e}")
                                
                                processed += 1
                                
                                # Small delay to avoid rate limits
                                time.sleep(0.1)
                                
                            except Exception as e:
                                logger.warning(f"Error processing email {msg_id}: {e}")
                                continue
                        
                        logger.info(f"[BACKFILL] Processed {processed} emails")
                        
                    except Exception as e:
                        logger.error(f"Gmail backfill failed: {e}")
                
                # Note: Chat messages are NOT backfilled - only new messages are processed on-the-fly
                # as they arrive. This keeps the memory system focused on current conversations.
                
                # Wait for background threads to complete (facts extraction)
                # Wait time scales with number of emails processed
                wait_time = min(5 + (stats['emails_processed'] * 0.1), 30)  # Max 30 seconds
                logger.info(f"[BACKFILL] Waiting {wait_time:.1f}s for background fact extraction threads to complete...")
                time.sleep(wait_time)
                
                # Calculate final stats
                final_facts_count = facts_col.count_documents({"user_id": user_id}) if facts_col is not None else 0
                final_relationships_count = relationships_col.count_documents({"user_id": user_id}) if relationships_col is not None else 0
                final_project_relationships_count = project_relationships_col.count_documents({"user_id": user_id}) if project_relationships_col is not None else 0
                final_projects_count = projects_col.count_documents({"user_id": user_id}) if projects_col is not None else 0
                
                stats["facts_extracted"] = max(0, final_facts_count - initial_facts_count)
                stats["relationships_updated"] = max(0, final_relationships_count - initial_relationships_count)
                stats["project_relationships_created"] = max(0, final_project_relationships_count - initial_project_relationships_count)
                stats["projects_created"] = max(0, final_projects_count - initial_projects_count)
                
                logger.info(f"[BACKFILL] Comprehensive backfill completed for user {user_id}")
                logger.info(f"[BACKFILL] Stats: {stats}")
                logger.info(f"[BACKFILL] Total facts: {final_facts_count} (new: {stats['facts_extracted']})")
                logger.info(f"[BACKFILL] Total relationships (old): {final_relationships_count} (new: {stats['relationships_updated']})")
                logger.info(f"[BACKFILL] Total project-contact relationships (new): {final_project_relationships_count} (new: {stats['project_relationships_created']})")
                logger.info(f"[BACKFILL] Total projects: {final_projects_count} (new: {stats['projects_created']})")
                logger.info(f"[BACKFILL] Emails processed: {stats['emails_processed']}, skipped: {stats.get('emails_skipped', 0)}")
                if stats.get("skipped_categories"):
                    logger.info(f"[BACKFILL] Skipped categories: {stats['skipped_categories']}")
                
            except Exception as e:
                logger.error(f"Comprehensive backfill failed: {e}", exc_info=True)
        
        # Run in background thread
        thread = threading.Thread(target=run_comprehensive_backfill, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "message": "Comprehensive backfill started in background",
            "user_id": user_id,
            "max_emails": max_emails
        })
        
    except Exception as e:
        logger.error(f"Error starting comprehensive backfill: {e}")
        return handle_api_error(e)


@memory_bp.route('/admin/backfill-email-facts', methods=['POST'])
def backfill_email_facts():
    """
    Backfill facts from existing emails (ADMIN ONLY).
    
    Expected JSON body:
    {
        "user_id": "user123",  // required
        "max_emails": 20      // optional - default: 20
    }
    
    Returns:
    {
        "success": true,
        "message": "Backfill started",
        "user_id": "user123",
        "max_emails": 20
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
        
        max_emails = int(data.get('max_emails', 20))
        
        # Extract facts directly from emails (no classification needed)
        from app.services.gmail_service import extract_facts_from_email
        from app.tools.email import _extract_plain_text
        from app.utils.oauth_utils import load_google_credentials
        from googleapiclient.discovery import build
        import threading
        
        def run_backfill():
            try:
                # Load credentials and build Gmail service
                creds = load_google_credentials(user_id)
                if not creds:
                    logger.error(f"No credentials found for user {user_id}")
                    return
                
                service = build("gmail", "v1", credentials=creds)
                
                # Fetch recent emails from inbox and sent
                logger.info(f"Fetching up to {max_emails} emails for fact extraction (user: {user_id})")
                resp = service.users().messages().list(
                    userId="me",
                    q="in:inbox OR in:sent",  # Include both received and sent emails
                    maxResults=max_emails * 2,  # Fetch more to account for threads
                ).execute()
                
                messages = resp.get("messages", []) or []
                seen_threads = set()
                processed = 0
                
                # Process emails sequentially to extract facts
                for msg_info in messages:
                    if processed >= max_emails:
                        break
                    
                    try:
                        msg_id = msg_info["id"]
                        
                        # Fetch full message
                        full_msg = service.users().messages().get(
                            userId="me",
                            id=msg_id,
                            format="full",
                        ).execute()
                        
                        thread_id = full_msg.get("threadId")
                        if thread_id in seen_threads:
                            continue  # Skip duplicate threads
                        seen_threads.add(thread_id)
                        
                        # Extract email data
                        headers = {h["name"]: h["value"] for h in full_msg.get("payload", {}).get("headers", [])}
                        
                        # Extract body text using the helper function
                        payload = full_msg.get("payload", {})
                        body = _extract_plain_text(payload)
                        
                        email_data = {
                            "thread_id": thread_id,  # Use thread_id (not threadId) for extract_facts_from_email
                            "from": headers.get("From", ""),
                            "subject": headers.get("Subject", "(No subject)"),
                            "snippet": full_msg.get("snippet", "")[:200],
                            "body": body[:2000],  # Limit body length
                        }
                        
                        # Extract facts from email (runs in background thread)
                        extract_facts_from_email(user_id, email_data)
                        processed += 1
                        
                        # Small delay to avoid rate limits
                        import time
                        time.sleep(0.1)
                        
                    except Exception as e:
                        logger.warning(f"Failed to process email {msg_id}: {e}")
                        continue
                
                logger.info(f"✅ Email fact extraction completed for user {user_id} ({processed} emails processed)")
            except Exception as e:
                logger.error(f"❌ Email fact backfill failed for user {user_id}: {e}")
        
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
        
        if messages_col is None or facts_col is None:
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


# ============================================================================
# Task Management Endpoints
# ============================================================================

@memory_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """
    List tasks for a user.
    
    Query parameters:
    - user_id (required): User ID
    - status: Filter by status (pending, in_progress, completed, cancelled)
    - source: Filter by source (email, chat, calendar, manual)
    - priority: Filter by priority (high, medium, low)
    - limit: Max results (default: 50)
    
    Returns:
    {
        "success": true,
        "tasks": [...],
        "count": 10
    }
    """
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "user_id is required"}), 400
        
        status = request.args.get('status')
        source = request.args.get('source')
        priority = request.args.get('priority')
        limit = int(request.args.get('limit', 50))
        
        tasks_col = get_tasks_collection()
        if tasks_col is None:
            return jsonify({"success": False, "error": "Tasks collection not available"}), 500
        
        # Build query
        query = {"user_id": user_id}
        if status:
            query["status"] = status
        if source:
            query["source"] = source
        if priority:
            query["priority"] = priority
        
        # Get tasks, sorted by priority and due date
        tasks = list(tasks_col.find(query).sort([
            ("priority", -1),  # High priority first
            ("due_date", 1),    # Then by due date
            ("created_at", -1)  # Then by creation date
        ]).limit(limit))
        
        # Convert ObjectId to string and format dates
        result_tasks = []
        for task in tasks:
            task_dict = dict(task)
            task_dict["_id"] = str(task_dict["_id"])
            
            # Convert datetime to ISO string
            for date_field in ["created_at", "updated_at", "due_date", "completed_at"]:
                if date_field in task_dict and task_dict[date_field]:
                    if isinstance(task_dict[date_field], datetime):
                        task_dict[date_field] = task_dict[date_field].isoformat()
            
            result_tasks.append(task_dict)
        
        return jsonify({
            "success": True,
            "tasks": result_tasks,
            "count": len(result_tasks)
        })
        
    except Exception as e:
        logger.error(f"Error listing tasks: {e}")
        return handle_api_error(e)


@memory_bp.route('/tasks', methods=['POST'])
def create_task():
    """
    Create a new task.
    
    Body:
    {
        "user_id": "v",
        "title": "Task title",
        "description": "Optional description",
        "priority": "high|medium|low",
        "status": "pending|in_progress",
        "due_date": "2024-01-01T00:00:00Z",
        "source": "manual|email|chat|calendar",
        "source_ref": "optional reference"
    }
    
    Returns:
    {
        "success": true,
        "task": {...},
        "task_id": "..."
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400
        
        user_id = data.get('user_id')
        title = data.get('title')
        
        if not user_id or not title:
            return jsonify({"success": False, "error": "user_id and title are required"}), 400
        
        tasks_col = get_tasks_collection()
        if tasks_col is None:
            return jsonify({"success": False, "error": "Tasks collection not available"}), 500
        
        from uuid import uuid4
        
        # Parse due_date if provided
        due_date = None
        if data.get('due_date'):
            try:
                if isinstance(data['due_date'], str):
                    from dateutil.parser import parse
                    due_date = parse(data['due_date'])
                else:
                    due_date = data['due_date']
            except Exception as e:
                logger.warning(f"Could not parse due_date: {e}")
        
        task = {
            "_id": str(uuid4()),
            "user_id": user_id,
            "title": title[:200],  # Limit title length
            "description": data.get('description'),
            "status": data.get('status', 'pending'),
            "priority": data.get('priority', 'medium'),
            "source": data.get('source', 'manual'),
            "source_ref": data.get('source_ref'),
            "due_date": due_date,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        tasks_col.insert_one(task)
        
        # Convert datetime to ISO string for response
        task_dict = dict(task)
        for date_field in ["created_at", "updated_at", "due_date"]:
            if date_field in task_dict and task_dict[date_field]:
                if isinstance(task_dict[date_field], datetime):
                    task_dict[date_field] = task_dict[date_field].isoformat()
        
        return jsonify({
            "success": True,
            "task": task_dict,
            "task_id": task["_id"]
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        return handle_api_error(e)


@memory_bp.route('/tasks/<task_id>', methods=['PUT'])
def update_task(task_id):
    """
    Update an existing task.
    
    Body (all fields optional):
    {
        "title": "New title",
        "description": "New description",
        "status": "pending|in_progress|completed|cancelled",
        "priority": "high|medium|low",
        "due_date": "2024-01-01T00:00:00Z"
    }
    
    Returns:
    {
        "success": true,
        "task": {...}
    }
    """
    try:
        data = request.get_json() or {}
        
        tasks_col = get_tasks_collection()
        if tasks_col is None:
            return jsonify({"success": False, "error": "Tasks collection not available"}), 500
        
        # Find task
        task = tasks_col.find_one({"_id": task_id})
        if not task:
            return jsonify({"success": False, "error": "Task not found"}), 404
        
        # Build update
        update = {"$set": {"updated_at": datetime.utcnow()}}
        
        if "title" in data:
            update["$set"]["title"] = data["title"][:200]
        if "description" in data:
            update["$set"]["description"] = data["description"]
        if "status" in data:
            update["$set"]["status"] = data["status"]
            # Set completed_at if status is completed
            if data["status"] == "completed":
                update["$set"]["completed_at"] = datetime.utcnow()
            elif "completed_at" in task:
                update["$unset"] = {"completed_at": ""}
        if "priority" in data:
            update["$set"]["priority"] = data["priority"]
        if "due_date" in data:
            if data["due_date"]:
                try:
                    if isinstance(data['due_date'], str):
                        from dateutil.parser import parse
                        update["$set"]["due_date"] = parse(data['due_date'])
                    else:
                        update["$set"]["due_date"] = data['due_date']
                except Exception as e:
                    logger.warning(f"Could not parse due_date: {e}")
            else:
                update["$unset"] = update.get("$unset", {})
                update["$unset"]["due_date"] = ""
        
        tasks_col.update_one({"_id": task_id}, update)
        
        # Get updated task
        updated_task = tasks_col.find_one({"_id": task_id})
        task_dict = dict(updated_task)
        task_dict["_id"] = str(task_dict["_id"])
        
        # Convert datetime to ISO string
        for date_field in ["created_at", "updated_at", "due_date", "completed_at"]:
            if date_field in task_dict and task_dict[date_field]:
                if isinstance(task_dict[date_field], datetime):
                    task_dict[date_field] = task_dict[date_field].isoformat()
        
        return jsonify({
            "success": True,
            "task": task_dict
        })
        
    except Exception as e:
        logger.error(f"Error updating task: {e}")
        return handle_api_error(e)


@memory_bp.route('/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """
    Delete a task.
    
    Returns:
    {
        "success": true,
        "message": "Task deleted"
    }
    """
    try:
        tasks_col = get_tasks_collection()
        if tasks_col is None:
            return jsonify({"success": False, "error": "Tasks collection not available"}), 500
        
        result = tasks_col.delete_one({"_id": task_id})
        
        if result.deleted_count == 0:
            return jsonify({"success": False, "error": "Task not found"}), 404
        
        return jsonify({
            "success": True,
            "message": "Task deleted"
        })
        
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        return handle_api_error(e)


# Export blueprint
__all__ = ['memory_bp']

