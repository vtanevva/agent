"""Gmail-related API routes."""

import json
import re
from flask import Blueprint, request, jsonify

from app.services.gmail_service import (
    get_thread_detail,
    reply_to_thread,
    forward_thread,
    archive_thread,
    mark_thread_handled,
    list_threads,
    search_threads,
    classify_single_email,
    triaged_inbox,
    classify_background,
    send_new_email,
    rewrite_email_text,
)
from app.tools.email import analyze_email_style, generate_reply_draft, generate_forward_draft
from app.utils.oauth_utils import require_google_auth
from app.utils.rate_limiter import enforce_rate_limit, get_rate_limit_key, RateLimitExceeded
from app.utils.logging_utils import get_logger
from app.config import Config
from app.db.collections import get_contacts_collection

logger = get_logger(__name__)

gmail_bp = Blueprint('gmail', __name__, url_prefix='/api/gmail')


def _normalize_user_id(user_id_raw: str) -> str:
    """
    Normalize user_id - ensure it's never "anonymous" or empty.
    Generates unique ID for anonymous users to ensure proper rate limiting.
    """
    if not user_id_raw or user_id_raw.strip().lower() == "anonymous":
        import uuid
        # Generate unique session-based ID
        unique_id = f"anon-{uuid.uuid4().hex[:12]}"
        logger.warning(f"Anonymous user_id detected, generated: {unique_id}")
        return unique_id
    return user_id_raw.strip().lower()


def _check_gmail_rate_limit(user_id: str):
    """Helper to check rate limit for Gmail endpoints."""
    if Config.RATE_LIMIT_ENABLED:
        from flask import request
        # Normalize user_id first
        normalized_user_id = _normalize_user_id(user_id)
        rate_limit_key = get_rate_limit_key(request, normalized_user_id)
        # Gmail endpoints: 10 requests per minute (cost control for Gmail API)
        enforce_rate_limit(
            key=rate_limit_key,
            max_requests=10,
            window_seconds=60,
            endpoint_name="gmail"
        )


def _lookup_contact_email(user_id: str, name_or_email: str) -> str:
    """
    Look up email address from contacts by name or return the input if it's already an email.

    Also handles natural language phrases like:
      - "an email to Marin"
      - "email Marin about the meeting"
    by extracting the most likely name/nickname segment before lookup.
    """
    if not name_or_email:
        return name_or_email

    original = name_or_email.strip()
    if "@" in original:
        return original

    # Try to extract a cleaner recipient name from phrases
    candidate = original
    lower = original.lower()

    # Patterns in order of specificity
    patterns = [
        r"send\s+an\s+email\s+to\s+(.+)",
        r"send\s+email\s+to\s+(.+)",
        r"send\s+an\s+email\s+(.+)",
        r"email\s+(.+)",
        r"an\s+email\s+to\s+(.+)",
    ]

    for pat in patterns:
        m = re.search(pat, original, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            break

    # Strip common trailing phrases after the name/nickname
    split_tokens = [" about ", " regarding ", " re: ", " re ", " with ", " on ", " for "]
    cand_lower = candidate.lower()
    cut_idx = None
    for tok in split_tokens:
        pos = cand_lower.find(tok)
        if pos != -1:
            cut_idx = pos
            break
    if cut_idx is not None:
        candidate = candidate[:cut_idx].strip()

    name_to_lookup = candidate or original

    contacts_col = get_contacts_collection()
    if contacts_col is None:
        return name_to_lookup
    
    name_lower = name_to_lookup.strip().lower()
    
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
    if contact and contact.get("email"):
        return contact.get("email")
    
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
    if contact and contact.get("email"):
        return contact.get("email")
    
    # If no match, fall back to cleaned candidate, not the full phrase
    return name_to_lookup


@gmail_bp.route("/list", methods=["POST"])
def gmail_list_threads():
    """List Gmail threads for a given label (default INBOX)."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    label = (data.get("label") or "INBOX").strip()
    max_results = int(data.get("max_results", 50))

    # Check rate limit
    _check_gmail_rate_limit(user_id)

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = list_threads(
        user_id=user_id,
        label=label,
        max_results=max_results
    )
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@gmail_bp.route("/search", methods=["POST"])
def gmail_search_threads():
    """Search Gmail messages and return unique threads for a query."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    query = (data.get("query") or "").strip()
    max_results = int(data.get("max_results", 20))

    if not query:
        return jsonify({"success": False, "error": "Missing query"}), 400

    # Check rate limit
    _check_gmail_rate_limit(user_id)

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = search_threads(
        user_id=user_id,
        query=query,
        max_results=max_results
    )
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@gmail_bp.route("/thread-detail", methods=["POST"])
def gmail_thread_detail():
    """Return full plain-text content and headers for the selected email/thread."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    thread_id = data.get("thread_id")
    if not thread_id:
        return jsonify({"success": False, "error": "Missing thread_id"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = get_thread_detail(
        user_id=user_id,
        thread_id=thread_id
    )
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@gmail_bp.route("/send", methods=["POST"])
def gmail_send_new():
    """Send a new email (compose)."""
    print("[DEBUG] /api/gmail/send endpoint hit!", flush=True)
    try:
        data = request.get_json(force=True, silent=True) or {}
        print(f"[DEBUG] Received data: to={data.get('to')}, subject={data.get('subject')}", flush=True)
        user_id_raw = data.get("user_id", "")
        user_id = _normalize_user_id(user_id_raw)
        to = data.get("to")
        subject = data.get("subject") or "(No subject)"
        body = data.get("body") or ""

        if not to or not body:
            return jsonify({"success": False, "error": "Missing 'to' or 'body'"}), 400

        # Look up contact if needed
        try:
            to = _lookup_contact_email(user_id, to)
        except Exception as e:
            logger.warning(f"Contact lookup failed for '{to}': {e}")
        
        # Validate email address format
        if "@" not in to or len(to.split("@")) != 2:
            return jsonify({"success": False, "error": f"Invalid email address: '{to}'. Please enter a valid email address."}), 400

        # Check rate limit
        if Config.RATE_LIMIT_ENABLED:
            try:
                rate_limit_key = get_rate_limit_key(request, user_id)
                enforce_rate_limit(
                    key=rate_limit_key,
                    max_requests=10,
                    window_seconds=60,
                    endpoint_name="gmail_send"
                )
            except RateLimitExceeded as e:
                return jsonify({"success": False, "error": str(e)}), 429

        # Check authentication
        try:
            auth_response = require_google_auth(user_id)
            if auth_response:
                return auth_response
        except Exception as e:
            logger.error(f"Auth check failed: {e}", exc_info=True)
            return jsonify({"success": False, "error": f"Authentication error: {str(e)}"}), 401

        # Send email
        try:
            result = send_new_email(
                user_id=user_id,
                to=to,
                subject=subject,
                body=body
            )
            if not isinstance(result, dict):
                logger.error(f"send_new_email returned non-dict: {result}")
                return jsonify({"success": False, "error": "Unexpected error occurred"}), 500
            
            status = 200 if result.get("success", True) else 500
            return jsonify(result), status
        except Exception as e:
            logger.error(f"Error in send_new_email: {e}", exc_info=True)
            return jsonify({"success": False, "error": f"Failed to send email: {str(e)}"}), 500
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Unexpected error in gmail_send_new: {e}\n{error_trace}", exc_info=True)
        return jsonify({"success": False, "error": f"Server error: {str(e)}"}), 500

@gmail_bp.route("/reply", methods=["POST"])
def gmail_reply_send():
    """Send a reply inside a Gmail thread with a provided body."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    thread_id = data.get("thread_id")
    to = data.get("to")
    body = data.get("body") or ""
    subj_prefix = data.get("subj_prefix", "Re:")

    if not all([thread_id, to, body]):
        return jsonify({"success": False, "error": "Missing thread_id, to, or body"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = reply_to_thread(
        user_id=user_id,
        thread_id=thread_id,
        to=to,
        body=body,
        subj_prefix=subj_prefix
    )
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@gmail_bp.route("/forward", methods=["POST"])
def gmail_forward_send():
    """Forward a Gmail thread to another recipient."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    thread_id = data.get("thread_id")
    to = data.get("to")
    body = data.get("body") or ""
    subj_prefix = data.get("subj_prefix", "Fwd:")

    if not all([thread_id, to]):
        return jsonify({"success": False, "error": "Missing thread_id or to"}), 400

    # Check rate limit (stricter for forward operations)
    if Config.RATE_LIMIT_ENABLED:
        rate_limit_key = get_rate_limit_key(request, user_id)
        enforce_rate_limit(
            key=rate_limit_key,
            max_requests=10,
            window_seconds=60,
            endpoint_name="gmail_forward"
        )

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = forward_thread(
        user_id=user_id,
        thread_id=thread_id,
        to=to,
        body=body,
        subj_prefix=subj_prefix
    )
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@gmail_bp.route("/archive", methods=["POST"])
def gmail_archive_thread():
    """Archive a Gmail thread by removing it from the INBOX."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    thread_id = data.get("thread_id")
    if not thread_id:
        return jsonify({"success": False, "error": "Missing thread_id"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = archive_thread(
        user_id=user_id,
        thread_id=thread_id
    )
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@gmail_bp.route("/mark-handled", methods=["POST"])
def gmail_mark_handled():
    """Apply a 'Handled' label to a thread and mark it as read."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    thread_id = data.get("thread_id")
    if not thread_id:
        return jsonify({"success": False, "error": "Missing thread_id"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = mark_thread_handled(
        user_id=user_id,
        thread_id=thread_id
    )
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@gmail_bp.route("/classify-email", methods=["POST"])
def gmail_classify_email():
    """Classify a single email using the Smart Inbox Triage system."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    
    # Email data can come from request or be fetched by thread_id
    thread_id = data.get("thread_id")
    email_data = data.get("email", {})
    
    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response
    
    result = classify_single_email(
        user_id=user_id,
        thread_id=thread_id,
        email_data=email_data or None
    )
    
    # Keep 400 response if request was structurally invalid
    if not result.get("success") and result.get("error") == "Missing email data or thread_id":
        return jsonify(result), 400
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@gmail_bp.route("/triaged-inbox", methods=["POST"])
def gmail_triaged_inbox():
    """Get triaged inbox with emails categorized by priority."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    max_results = int(data.get("max_results", 50))
    category_filter = data.get("category")  # Optional: filter by specific category

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = triaged_inbox(
        user_id=user_id,
        max_results=max_results,
        category_filter=category_filter
    )
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@gmail_bp.route("/classify-background", methods=["POST"])
def gmail_classify_background():
    """Trigger background classification for unclassified emails. Returns immediately."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    max_emails = int(data.get("max_emails", 20))

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = classify_background(
        user_id=user_id,
        max_emails=max_emails
    )
    status = 200 if result.get("success", True) else 500
    return jsonify(result), status


@gmail_bp.route("/analyze-style", methods=["POST"])
def gmail_analyze_style():
    """Analyze user's email writing style from Sent messages."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    max_samples = int(data.get("max_samples", 10))

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    result = analyze_email_style(
        user_id=user_id,
        max_samples=max_samples
    )
    # analyze_email_style returns a JSON string, so parse it first
    try:
        result_dict = json.loads(result) if isinstance(result, str) else result
        return jsonify(result_dict)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to parse style analysis: {str(e)}"}), 500


@gmail_bp.route("/draft-reply", methods=["POST"])
def gmail_draft_reply():
    """Generate a reply draft for a given thread, emulating user's style."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    thread_id = data.get("thread_id")
    to = data.get("to")
    user_points = data.get("user_points") or ""
    max_samples = int(data.get("max_samples", 10))

    if not all([thread_id, to]):
        return jsonify({"success": False, "error": "Missing thread_id or to"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    try:
        result = generate_reply_draft(
            user_id=user_id,
            thread_id=thread_id,
            to=to,
            user_points=user_points,
            max_samples=max_samples
        )
        print(f"[DEBUG] generate_reply_draft returned: {result[:200] if len(str(result)) > 200 else result}")
        print(f"[DEBUG] Result type: {type(result)}")
        
        # generate_reply_draft returns a JSON string, so parse it first
        result_dict = json.loads(result) if isinstance(result, str) else result
        print(f"[DEBUG] Parsed result: {result_dict}")
        return jsonify(result_dict)
    except Exception as e:
        print(f"[ERROR] Draft generation failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to generate draft: {str(e)}"}), 500


@gmail_bp.route("/draft-forward", methods=["POST"])
def gmail_draft_forward():
    """Generate a forward draft for a given thread, emulating user's style."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    thread_id = data.get("thread_id")
    to = data.get("to") or ""
    user_points = data.get("user_points") or ""
    max_samples = int(data.get("max_samples", 10))

    if not thread_id:
        return jsonify({"success": False, "error": "Missing thread_id"}), 400

    auth_response = require_google_auth(user_id)
    if auth_response:
        return auth_response

    try:
        result = generate_forward_draft(
            user_id=user_id,
            thread_id=thread_id,
            to=to,
            user_points=user_points,
            max_samples=max_samples
        )
        result_dict = json.loads(result) if isinstance(result, str) else result
        return jsonify(result_dict)
    except Exception as e:
        print(f"[ERROR] Forward draft generation failed: {e}", flush=True)
        return jsonify({"success": False, "error": f"Failed to generate forward draft: {str(e)}"}), 500


@gmail_bp.route("/rewrite", methods=["POST"])
def gmail_rewrite_text():
    """Rewrite a user-provided text more politely/clearly."""
    data = request.get_json(force=True, silent=True) or {}
    user_id_raw = data.get("user_id", "")
    user_id = _normalize_user_id(user_id_raw)
    text = (data.get("text") or "").strip()
    tone = (data.get("tone") or "polite and professional").strip()
    include_signature = bool(data.get("include_signature", False))
    signature_text = (data.get("signature") or "").strip()
    generate_subject = bool(data.get("generate_subject", True))

    if not text:
        return jsonify({"success": False, "error": "Missing 'text'"}), 400

    result = rewrite_email_text(
        user_id=user_id,
        text=text,
        tone=tone,
        include_signature=include_signature,
        signature_text=signature_text,
        generate_subject=generate_subject
    )
    
    # Transform service response to match frontend expectations
    if result.get("success") and result.get("result"):
        result_data = result["result"]
        return jsonify({
            "success": True,
            "rewritten": result_data.get("body", ""),
            "subject": result_data.get("subject", "")
        })
    else:
        # Return error if rewrite failed - include error message for debugging
        error_msg = result.get("error", "Unknown error occurred")
        logger.error(f"Rewrite failed for user {user_id}: {error_msg}")
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500

