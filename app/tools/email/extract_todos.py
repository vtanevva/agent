"""Tool: extract_todos_from_thread — extract actionable TODOs from an email thread and store in MongoDB."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.db.collections import get_email_todos_collection
from app.services.llm_service import get_llm_service
from app.tools.email.detail import get_thread_detail as tool_get_thread_detail
from app.utils.logging_utils import get_logger
from app.utils.tool_registry import register, ToolSchema

logger = get_logger(__name__)

PROMPT_VERSION = "1.1"


def _best_effort_json_parse(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    s = text.strip()
    try:
        return json.loads(s)
    except Exception:
        pass

    # Try to extract the first JSON object from the response
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _normalize_todos(raw: Any) -> List[Dict[str, Any]]:
    todos: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return todos

    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                todos.append({"text": text, "due": None, "assignee": "me", "confidence": 0.5})
            continue

        if not isinstance(item, dict):
            continue

        text = str(item.get("text") or item.get("task") or "").strip()
        if not text:
            continue

        due = item.get("due")
        if isinstance(due, str):
            due = due.strip() or None
        elif due is not None:
            due = str(due)

        assignee = item.get("assignee")
        if isinstance(assignee, str):
            assignee = assignee.strip() or "me"
        elif assignee is None:
            assignee = "me"
        else:
            assignee = str(assignee)

        confidence = item.get("confidence", 0.6)
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.6
        confidence = max(0.0, min(1.0, confidence))

        todos.append(
            {
                "text": text,
                "due": due,
                "assignee": assignee,
                "confidence": confidence,
                "source_quote": (item.get("source_quote") or item.get("quote") or None),
            }
        )

    # De-dupe by normalized text
    seen = set()
    deduped = []
    for t in todos:
        key = re.sub(r"\s+", " ", (t.get("text") or "").strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    return deduped


def _is_generic_or_email_level_task(text: str, subject: str) -> bool:
    """
    Filter out non-actionable, generic, or "whole-email as task" items like:
    - "Read this email"
    - "Handle/Process/Review email about <subject>"
    - "Follow up" with no concrete action
    """
    if not text:
        return True

    t = re.sub(r"\s+", " ", text.strip()).lower()
    subj = re.sub(r"\s+", " ", (subject or "").strip()).lower()

    # Too long usually means it's a summary, not a task
    if len(t) > 220:
        return True

    generic_starts = (
        "read this email",
        "read the email",
        "review this email",
        "review the email",
        "go through this email",
        "process this email",
        "handle this email",
        "handle this thread",
        "handle this conversation",
        "deal with this email",
        "deal with this thread",
        "check this email",
        "look at this email",
        "look into this email",
    )
    if any(t.startswith(p) for p in generic_starts):
        return True

    # "Follow up" alone is not a task; require specifics
    if t in {"follow up", "follow-up", "followup"}:
        return True

    # Avoid tasks that are basically just the subject line
    if subj and (t == subj or t.startswith(subj + " ") or subj.startswith(t)):
        return True

    # Common "email about X" vague task
    if "email about" in t or "thread about" in t:
        # Allow if it includes a concrete action verb beyond "email/thread about"
        if not re.search(r"\b(prepare|create|draft|send|book|schedule|call|meet|present|submit|finish|deliver|update|share|attach|review|approve|sign|pay|confirm)\b", t):
            return True

    return False


def extract_todos_from_thread(user_id: str, thread_id: str) -> str:
    """
    Extract TODO items from a Gmail thread and store them in MongoDB.

    Returns JSON:
    {
      "success": true,
      "thread_id": "...",
      "todos": [{"text": "...", "due": null, "assignee": "me", "confidence": 0.7}],
      "stored": true
    }
    """
    if not user_id or not thread_id:
        return json.dumps({"success": False, "error": "Missing user_id or thread_id"})

    # Fetch email content (subject/from/date/body)
    try:
        detail_raw = tool_get_thread_detail(user_id=user_id, thread_id=thread_id)
        detail = json.loads(detail_raw) if isinstance(detail_raw, str) else (detail_raw or {})
    except Exception as e:
        return json.dumps({"success": False, "error": f"Failed to load thread detail: {str(e)}"})

    if not detail.get("success"):
        return json.dumps({"success": False, "error": detail.get("error", "Failed to load thread detail")})

    subject = detail.get("subject", "(No subject)")
    sender = detail.get("from", "")
    date = detail.get("date", "")
    body = (detail.get("body") or "").strip()

    if not body:
        return json.dumps({"success": True, "thread_id": thread_id, "todos": [], "stored": False, "note": "Empty email body"})

    llm = get_llm_service()

    prompt = (
        "Extract actionable TODO items for the user from this email.\n\n"
        "Very important:\n"
        "- Do NOT turn the whole email/thread into a single task (no 'Handle this email', 'Review this thread', etc.).\n"
        "- Only extract concrete actions explicitly requested or clearly implied by the message.\n"
        "- If the email says the user must do a presentation, create a task like 'Prepare presentation for <topic>'.\n"
        "- Prefer tasks assigned to the recipient (the user). If unclear, set assignee='me'.\n"
        "- If a due date/time is mentioned, copy it as a short string (do NOT invent dates).\n"
        "- Keep each task short and specific (ideally <= 12 words).\n"
        "- ALWAYS include a short exact quote from the email for each task (source_quote).\n"
        "- Return at most 10 todos.\n\n"
        "Return STRICT JSON with exactly this shape:\n"
        "{\"todos\":[{\"text\":string,\"due\":string|null,\"assignee\":string,\"confidence\":number,\"source_quote\":string|null}]}\n"
        "Return an empty todos array if none.\n\n"
        "Examples (good):\n"
        "- Email: 'Can you prepare the Q1 presentation by Friday?' -> text='Prepare Q1 presentation', due='Friday'\n"
        "- Email: 'Please send me the invoice PDF' -> text='Send invoice PDF'\n"
        "Examples (bad):\n"
        "- 'Read this email'\n"
        "- 'Handle email about Q1'\n\n"
        f"Subject: {subject}\n"
        f"From: {sender}\n"
        f"Date: {date}\n\n"
        f"Body:\n{body[:6000]}\n"
    )

    try:
        resp_text = llm.chat_completion_text(
            messages=[
                {"role": "system", "content": "You are a careful assistant that extracts TODO items from emails and outputs strict JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=600,
        )
    except Exception as e:
        logger.error(f"Todo extraction LLM call failed: {e}", exc_info=True)
        return json.dumps({"success": False, "error": "LLM extraction failed"})

    parsed = _best_effort_json_parse(resp_text) or {}
    todos = _normalize_todos(parsed.get("todos"))
    # Post-filter generic / whole-email tasks
    todos = [t for t in todos if not _is_generic_or_email_level_task(str(t.get("text") or ""), subject)]
    # Hard cap (defense-in-depth)
    todos = todos[:10]

    stored = False
    col = get_email_todos_collection()
    if col is not None:
        try:
            now = datetime.utcnow()
            col.update_one(
                {"user_id": user_id, "thread_id": thread_id},
                {
                    "$set": {
                        "user_id": user_id,
                        "thread_id": thread_id,
                        "subject": subject,
                        "from": sender,
                        "date": date,
                        "todos": todos,
                        "extracted_at": now,
                        "prompt_version": PROMPT_VERSION,
                        "model": llm.default_model,
                    }
                },
                upsert=True,
            )
            stored = True
        except Exception as e:
            logger.error(f"Failed to store email todos: {e}", exc_info=True)
            stored = False

    return json.dumps(
        {
            "success": True,
            "thread_id": thread_id,
            "subject": subject,
            "from": sender,
            "date": date,
            "todos": todos,
            "stored": stored,
        },
        ensure_ascii=False,
    )


# Register the tool (no-op registry, kept for compatibility)
register(
    extract_todos_from_thread,
    ToolSchema(
        name="extract_todos_from_thread",
        description="Extract TODO items from a Gmail thread and store them in MongoDB (email_todos).",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "thread_id": {"type": "string"},
            },
            "required": ["user_id", "thread_id"],
        },
    ),
)


