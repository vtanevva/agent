import json
import os
import sys

# UTF-8 stdout on Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, "backend")

from services.marketing_email_signals import (
    is_automated_or_bulk_sender,
    is_likely_marketing_or_newsletter,
    should_suppress_as_non_actionable,
)
from storage.sqlite_db import get_conn


def safe_json(v):
    try:
        return json.loads(v) if isinstance(v, str) else (v or {})
    except Exception:
        return {}


def row_subject(payload, cls):
    return str(payload.get("subject") or cls.get("title") or "").strip()


def row_sender(payload, row):
    user = row["user"] if "user" in row.keys() else None
    return str(
        payload.get("from")
        or payload.get("sender")
        or user
        or ""
    )


def row_body(payload, row):
    text = row["text"] if "text" in row.keys() else None
    return str(
        text
        or payload.get("text")
        or payload.get("body")
        or payload.get("snippet")
        or ""
    )


with get_conn() as c:
    rows = c.execute(
        """
        SELECT id, source, source_id, channel, ts, user, text,
               payload_json, classification_type, classification_json, created_at
        FROM messages
        WHERE lower(source) = 'gmail'
        ORDER BY id DESC
        LIMIT 60
        """
    ).fetchall()

print(f"scanned {len(rows)} gmail rows\n")

actionable = 0
suppressed = 0
escaped = []

for r in rows:
    cls = safe_json(r["classification_json"])
    payload = safe_json(r["payload_json"])

    ctype = str(r["classification_type"] or "").strip().upper()
    has_action = bool(cls.get("has_action") is True or cls.get("has_action") == 1)
    reply_type = str(cls.get("reply_type") or "none").strip().lower()
    is_actionable = (
        ctype == "ACTION"
        or has_action
        or reply_type in {"short", "time_relevant", "context_relevant"}
    )
    if not is_actionable:
        continue
    actionable += 1

    subject = row_subject(payload, cls)
    sender = row_sender(payload, r)
    body = row_body(payload, r)

    ok, reason = should_suppress_as_non_actionable(
        payload=payload, subject=subject, raw_text=body, sender=sender
    )
    if ok:
        suppressed += 1
        continue

    # Not suppressed -> this item would appear in the tasks list.
    headers_raw = payload.get("headers")
    header_count = 0
    if isinstance(headers_raw, list):
        header_count = len(headers_raw)
    elif isinstance(headers_raw, dict):
        header_count = len(headers_raw)

    escaped.append(
        {
            "id": r["id"],
            "subject": subject[:120],
            "sender": sender[:120],
            "classification_type": ctype,
            "has_action": has_action,
            "reply_type": reply_type,
            "header_count": header_count,
            "body_preview": body.strip()[:160],
        }
    )

print(f"actionable_after_broadened_rule = {actionable}")
print(f"suppressed_by_filter            = {suppressed}")
print(f"still_visible                   = {len(escaped)}\n")

for e in escaped:
    print("-" * 60)
    for k, v in e.items():
        print(f"{k:20s}: {v}")
