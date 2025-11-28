"""Chat-related API routes."""

import json
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify

from app.agents.orchestrator import get_orchestrator
# Session memory now handled by orchestrator via MemoryService
from app.chat_embeddings import extract_facts_with_gpt, save_chat_to_memory
from app.db.collections import get_conversations_collection, get_contacts_collection
from app.utils.oauth_utils import require_google_auth


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
    
    # Extract and store contact notes in background
    try:
        _extract_contact_notes(user_id, user_message, bot_reply)
    except Exception as e:
        print(f"[ERROR] Failed to extract contact notes: {e}", flush=True)


def _extract_contact_notes(user_id: str, user_message: str, bot_reply: str):
    """Extract contact-related information from conversation and store as notes."""
    from app.services.llm_service import get_llm_service
    
    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return
    
    llm_service = get_llm_service()
    
    # Get all contacts for this user
    contacts = list(contacts_col.find({"user_id": user_id}, {"email": 1, "name": 1, "nickname": 1}))
    if not contacts:
        return
    
    # Check if conversation mentions any contacts
    conversation_text = f"{user_message} {bot_reply}".lower()
    mentioned_contacts = []
    
    for contact in contacts:
        email = (contact.get("email") or "").lower()
        name = (contact.get("name") or "").lower()
        nickname = (contact.get("nickname") or "").lower()
        
        # Check if contact is mentioned
        if email and email in conversation_text:
            mentioned_contacts.append(contact)
        elif name and name in conversation_text:
            mentioned_contacts.append(contact)
        elif nickname and nickname in conversation_text:
            mentioned_contacts.append(contact)
    
    if not mentioned_contacts:
        return
    
    # Extract notes for each mentioned contact
    for contact in mentioned_contacts:
        try:
            email = contact.get("email", "")
            contact_name = contact.get("name", "")
            contact_nickname = contact.get("nickname", "")
            
            # Build prompt to extract contact-specific information
            prompt = f"""Extract and summarize any relevant information about this contact from the conversation.
Contact: {contact_name or email} {f'("{contact_nickname}")' if contact_nickname else ''}
Email: {email}

Conversation:
User: {user_message}
Assistant: {bot_reply}

Extract any:
- Personal details mentioned (work, interests, preferences, etc.)
- Relationship context
- Important facts or events
- Communication style or preferences

Return a concise summary (2-3 sentences) or "None" if nothing relevant was mentioned.
Summary:"""
            
            # Use LLM service to extract notes
            messages = [
                {"role": "system", "content": "You are a contact information extractor. Extract relevant information about contacts from conversations."},
                {"role": "user", "content": prompt},
            ]
            
            extracted_note = llm_service.chat_completion_text(
                messages=messages,
                model="gpt-3.5-turbo",
                max_tokens=150,
                temperature=0.3,
            )
            
            # Skip if no relevant information
            if not extracted_note or extracted_note.lower() == "none" or len(extracted_note) < 10:
                continue
            
            # Get existing notes
            existing_contact = contacts_col.find_one({"user_id": user_id, "email": email})
            existing_notes = existing_contact.get("notes", "") if existing_contact else ""
            
            # Combine with existing notes (keep last 5 notes to avoid bloat)
            if existing_notes:
                # Split existing notes by newlines or periods to get individual notes
                notes_list = [n.strip() for n in existing_notes.split("\n\n") if n.strip()]
                notes_list.append(f"[{datetime.utcnow().strftime('%Y-%m-%d')}] {extracted_note}")
                # Keep only last 5 notes
                notes_list = notes_list[-5:]
                updated_notes = "\n\n".join(notes_list)
            else:
                updated_notes = f"[{datetime.utcnow().strftime('%Y-%m-%d')}] {extracted_note}"
            
            # Update contact with new notes
            contacts_col.update_one(
                {"user_id": user_id, "email": email},
                {"$set": {"notes": updated_notes, "notes_updated_at": datetime.utcnow().isoformat()}},
            )
            
        except Exception as e:
            print(f"[ERROR] Failed to extract notes for contact {contact.get('email')}: {e}", flush=True)
            continue


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
    """Main chat endpoint that handles user messages."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        user_message = (data.get("message") or "").strip()
        user_id = (data.get("user_id") or "anonymous").strip().lower()
        session_id = data.get("session_id") or f"{user_id}-{uuid.uuid4().hex[:8]}"

        if not user_message:
            return jsonify({"reply": "No message received. Please enter something."}), 400

        # Get orchestrator and handle chat
        orchestrator = get_orchestrator()
        intent, reply = orchestrator.handle_chat(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
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

        # Save conversation
        save_message(user_id, session_id, user_message, reply)

        # Extract and save new facts
        extracted = extract_facts_with_gpt(user_message)
        for line in extracted.split("\n"):
            line = line.strip("- ").strip()
            if line and line.lower() != "none":
                fact = line.removeprefix("FACT:").strip()
                save_chat_to_memory(fact, session_id, user_id=user_id, emotion="neutral")

        return jsonify({"reply": reply})

    except Exception as e:
        print(f"[ERROR] Error in chat endpoint: {e}", flush=True)
        return jsonify({"error": "Invalid request", "message": str(e)}), 400

