"""Chat-related API routes."""

import json
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify

from app.agents.orchestrator import get_orchestrator
from app.services.memory_service import get_memory_service
from app.services.llm_service import get_llm_service
from app.db.collections import get_conversations_collection, get_contacts_collection
from app.utils.oauth_utils import require_google_auth
from app.utils.logging_utils import get_logger
from app.utils.rate_limiter import enforce_rate_limit, get_rate_limit_key, get_rate_limit_headers
from app.config import Config

logger = get_logger(__name__)


chat_bp = Blueprint('chat', __name__, url_prefix='/api')


def save_message(user_id, session_id, user_message, bot_reply):
    """Save a message pair (user + bot) to MongoDB"""
    conversations = get_conversations_collection()
    if conversations is None:
        return
    try:
        message_pair = {
            "timestamp": datetime.utcnow().isoformat(),
            "role": "user",
            "text": user_message,
        }
        bot_response = {
            "timestamp": datetime.utcnow().isoformat(),
            "role": "bot",
            "text": bot_reply,
        }
        conversations.update_one(
            {"user_id": user_id, "session_id": session_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "session_id": session_id,
                    "created_at": datetime.utcnow(),
                },
                "$push": {"messages": {"$each": [message_pair, bot_response]}},
            },
            upsert=True,
        )
    except Exception as e:
        print(f"[ERROR] Failed to save message: {e}", flush=True)
    


def _lookup_contact_email(user_id: str, name_or_email: str) -> str:
    """Look up email address from contacts by name or return the input if it's already an email."""
    if not name_or_email or "@" in name_or_email:
        return name_or_email
    
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return name_or_email
    
    name_lower = name_or_email.strip().lower()
    
    # Try exact match first
    contact = contacts_col.find_one(
        {
            "user_id": user_id,
            "$or": [
                {"name": {"$regex": f"^{name_lower}$", "$options": "i"}},
                {"nickname": {"$regex": f"^{name_lower}$", "$options": "i"}},
            ]
        },
        {"email": 1}
    )
    if contact:
        return contact.get("email", name_or_email)
    
    # Try word boundary match
    contact = contacts_col.find_one(
        {
            "user_id": user_id,
            "$or": [
                {"name": {"$regex": f"\\b{name_lower}\\b", "$options": "i"}},
                {"nickname": {"$regex": f"\\b{name_lower}\\b", "$options": "i"}},
            ]
        },
        {"email": 1}
    )
    if contact:
        return contact.get("email", name_or_email)
    
    return name_or_email


@chat_bp.route("/chat", methods=["POST"])
def chat():
    """Main chat endpoint that handles user messages with optional image attachments."""
    try:
        # Get request data
        if not request.is_json:
            logger.warning("Request is not JSON, content-type:", request.content_type)
            return jsonify({"error": "Request must be JSON", "message": "Content-Type must be application/json"}), 400
        
        data = request.get_json(force=True, silent=True) or {}
        logger.debug(f"Received chat request: keys={list(data.keys())}, has_message={'message' in data}, has_images={'images' in data}")
        
        user_message = (data.get("message") or "").strip()
        user_id_raw = data.get("user_id", "").strip()
        message_type = data.get("message_type")  # Optional: "calendar", "email", "contacts", "general"
        
        # Ensure user_id is never "anonymous" or empty - generate unique ID if needed
        # This ensures proper per-user rate limiting
        if not user_id_raw or user_id_raw.lower() == "anonymous":
            # Generate a session-based unique ID for anonymous users
            # This ensures each anonymous session gets its own rate limit
            session_id_temp = data.get("session_id") or f"anon-{uuid.uuid4().hex[:12]}"
            user_id = f"anon-{session_id_temp.split('-')[-1]}"
            logger.warning(f"Missing or anonymous user_id, generated: {user_id}")
        else:
            user_id = user_id_raw.lower()
        
        session_id = data.get("session_id") or f"{user_id}-{uuid.uuid4().hex[:8]}"
        
        # Enforce rate limiting (only if enabled in config)
        if Config.RATE_LIMIT_ENABLED:
            rate_limit_key = get_rate_limit_key(request, user_id)
            # Chat endpoint: 10 requests per minute (configurable via RATE_LIMIT_PER_MINUTE)
            # This limit helps control OpenAI API costs while allowing normal conversation flow
            max_requests = Config.RATE_LIMIT_PER_MINUTE if Config.RATE_LIMIT_PER_MINUTE > 0 else 10
            enforce_rate_limit(
                key=rate_limit_key,
                max_requests=max_requests,
                window_seconds=60,
                endpoint_name="chat"
            )
        
        # Handle images - ensure it's a list, not None or undefined
        images_raw = data.get("images")
        if images_raw is None or images_raw == "undefined":
            images = []
        elif isinstance(images_raw, list):
            images = images_raw
        else:
            images = []

        if not user_message and not images:
            logger.warning(f"Empty request: user_message='{user_message}', images_count={len(images)}")
            return jsonify({"error": "No message or image received", "message": "Please enter something."}), 400

        # Build message with images if provided
        if images:
            # For vision-capable models, format message with images
            content = []
            if user_message:
                content.append({"type": "text", "text": user_message})
            
            for image_data_uri in images:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": image_data_uri
                    }
                })
            
            # Store formatted message for orchestrator
            # The orchestrator will pass this to agents, which will use LLM with vision
            user_message_with_images = json.dumps({
                "text": user_message or "What's in this image?",
                "images": images,
                "content": content  # OpenAI format
            })
        else:
            user_message_with_images = user_message

        # Get orchestrator and handle chat
        orchestrator = get_orchestrator()
        intent, reply = orchestrator.handle_chat(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message_with_images,
            message_type=message_type,  # Pass explicit message_type if provided
        )

        # Preserve compose-modal behaviour for email-style replies
        if intent == "email":
            try:
                compose_data = json.loads(reply)
                if isinstance(compose_data, dict) and compose_data.get("action") == "open_compose":
                    # Look up contact email if needed
                    to = compose_data.get("to", "")
                    to = _lookup_contact_email(user_id, to)
                    compose_data["to"] = to
                    # Return special response for UI to open compose modal
                    return jsonify({
                        "reply": f"I'll help you compose an email to {to}.",
                        "compose": compose_data
                    })
            except (json.JSONDecodeError, ValueError, TypeError):
                # Not a JSON response, continue normally
                pass

        # Check if reply is calendar JSON (for calendar UI)
        if intent == "calendar":
            try:
                # Try to parse as JSON
                parsed_reply = json.loads(reply)
                if isinstance(parsed_reply, dict) and "success" in parsed_reply:
                    # This is a calendar JSON response - return it directly so frontend can parse it
                    # The frontend will check for parsed.success and parsed.events
                    events_count = len(parsed_reply.get('events', []))
                    logger.info(f"Calendar JSON response detected: success={parsed_reply.get('success')}, events_count={events_count}")
                    save_message(user_id, session_id, user_message or (f"[{len(images)} image(s)]" if images else ""), "📅 Calendar events displayed")
                    # Return JSON string so frontend can parse it
                    return jsonify({"reply": reply})
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                # Not JSON, continue normally - might be an error message
                logger.debug(f"Calendar reply is not JSON (might be error message): {e}, reply={reply[:100]}")
                pass

        # Save conversation (save text message, images are stored separately)
        save_message(user_id, session_id, user_message or (f"[{len(images)} image(s)]" if images else ""), reply)

        # ===== NEW USER AWARENESS INGESTION =====
        # Ingest user message into the new memory system for fact extraction
        try:
            from app.memory.ingestion_service import get_ingestion_service
            from app.memory.models import MessageDirection
            
            ingestion_service = get_ingestion_service()
            ingestion_service.ingest_message(
                    user_id=user_id,
                thread_id=session_id,
                channel="web_chat",
                direction=MessageDirection.INCOMING,  # Fixed: was .IN, should be .INCOMING
                text=user_message,
                extract_facts=True,  # Extract facts in background
            )
        except Exception as e:
            logger.warning(f"Failed to ingest message into User Awareness system: {e}")
        
        # ===== TASK EXTRACTION FROM CHAT =====
        # Extract actionable tasks from user messages
        try:
            from app.memory.models import get_tasks_collection
            from app.services.llm_service import get_llm_service
            from uuid import uuid4
            import json
            
            # Check if message contains task-like language
            task_keywords = ["todo", "task", "remind me", "need to", "should", "must", "have to", "don't forget"]
            if user_message and any(keyword in user_message.lower() for keyword in task_keywords):
                # Extract task using LLM
                llm_service = get_llm_service()
                task_prompt = f"""Extract any actionable tasks from this message. Return JSON:
{{
    "tasks": [
        {{"title": "Task description", "priority": "high|medium|low"}}
    ]
}}

Message: {user_message}

If no clear task, return {{"tasks": []}}"""

                try:
                    task_response = llm_service.chat_completion_text(
                        messages=[
                            {"role": "system", "content": "Extract tasks from messages. Return only JSON."},
                            {"role": "user", "content": task_prompt}
                        ],
                        temperature=0.1,
                        max_tokens=200
                    )
                    
                    # Parse JSON response
                    task_data = {}
                    try:
                        task_data = json.loads(task_response)
                    except json.JSONDecodeError:
                        # Try to extract JSON from response
                        import re
                        json_match = re.search(r'\{[\s\S]*\}', task_response)
                        if json_match:
                            task_data = json.loads(json_match.group(0))
                    
                    tasks_col = get_tasks_collection()
                    
                    if tasks_col and task_data.get("tasks"):
                        for task_item in task_data["tasks"]:
                            task_title = task_item.get("title", "").strip()
                            if not task_title:
                                continue
                            
                            task = {
                                "_id": str(uuid4()),
                                "user_id": user_id,
                                "title": task_title[:200],  # Limit title length
                                "description": task_title if len(task_title) > 200 else None,
                                "status": "pending",
                                "priority": task_item.get("priority", "medium"),
                                "source": "chat",
                                "source_ref": session_id,
                                "created_at": datetime.utcnow(),
                                "updated_at": datetime.utcnow()
                            }
                            
                            # Deduplicate - check if similar task already exists
                            existing = tasks_col.find_one({
                                "user_id": user_id,
                                "title": task["title"],
                                "status": {"$ne": "completed"}
                            })
                            
                            if not existing:
                                tasks_col.insert_one(task)
                                logger.info(f"Created task from chat: {task['title'][:50]}...")
                except Exception as e:
                    logger.warning(f"Task extraction from chat failed: {e}")
        except Exception as e:
            logger.warning(f"Task extraction setup failed: {e}")
        
        # Add rate limit headers to response (if rate limiting is enabled)
        response = jsonify({"reply": reply})
        if Config.RATE_LIMIT_ENABLED:
            rate_limit_key = get_rate_limit_key(request, user_id)
            max_requests = Config.RATE_LIMIT_PER_MINUTE if Config.RATE_LIMIT_PER_MINUTE > 0 else 10
            headers = get_rate_limit_headers(rate_limit_key, max_requests, 60)
            for key, value in headers.items():
                response.headers[key] = value
        
        return response

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Full traceback: {error_trace}")
        return jsonify({
            "error": "Invalid request",
            "message": str(e),
            "type": type(e).__name__
        }), 400

