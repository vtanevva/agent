"""Gmail detail utilities for fetching full message content for a thread or message."""

import base64
import json
from typing import Dict, Optional

from app.utils.google_api_helpers import get_gmail_service


def _extract_plain_text(payload: Dict) -> str:
    """Recursively prefer text/plain; fallback to stripped text/html."""
    if not payload:
        return ""

    # Helper to decode a body dict
    def decode_body(body: Dict) -> str:
        data = (body or {}).get("data")
        if not data:
            return ""
        try:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    # HTML stripper and entity unescaper
    import re, html as htmlmod
    def strip_html(html: str) -> str:
        # Normalize breaks then remove style/script and tags
        text = re.sub(r"(?i)<br\s*/?>", "\n", html)
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", "", text)
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", "", text)
        text = re.sub(r"(?s)<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return htmlmod.unescape(text).strip()

    # 1) If this node is multipart, skip direct body and inspect parts
    mime = (payload.get("mimeType") or "").lower()
    if not mime.startswith("multipart/"):
        direct = decode_body(payload.get("body", {}))
        # Ignore trivial bodies like "96" or very short tokens with no text
        if direct and (len(direct.strip()) >= 8 or any(c.isalpha() for c in direct)):
            if mime.startswith("text/html"):
                return strip_html(direct)
            return direct

    def is_meaningful(text: str) -> bool:
        if not text:
            return False
        s = text.strip()
        return (len(s) >= 8) and any(ch.isalpha() for ch in s)

    # 2) Look for text/plain anywhere in the tree, but avoid trivial content like "96"
    parts = payload.get("parts") or []
    best_plain = None
    best_html = None
    for p in parts:
        mt = (p.get("mimeType") or "").lower()
        if mt.startswith("text/plain"):
            text = decode_body(p.get("body", {}))
            if text:
                if is_meaningful(text):
                    return text
                best_plain = text if best_plain is None or len(text) > len(best_plain) else best_plain
        if mt.startswith("text/html"):
            html = decode_body(p.get("body", {}))
            if html:
                stripped = strip_html(html)
                if is_meaningful(stripped):
                    best_html = stripped if best_html is None or len(stripped) > len(best_html) else best_html
        # Recurse for nested multiparts
        nested = _extract_plain_text(p)
        if nested and is_meaningful(nested):
            # Only accept nested if it is not empty and not raw HTML with tags
            return nested

    # 3) Fallback: first available text/html (strip tags)
    # Search depth-first for html parts
    for p in parts:
        mt = (p.get("mimeType") or "").lower()
        if mt.startswith("text/html"):
            html = decode_body(p.get("body", {}))
            if html:
                return strip_html(html)
        nested_parts = p.get("parts")
        if nested_parts:
            nested_payload = {"parts": nested_parts}
            nested_text = _extract_plain_text(nested_payload)
            if nested_text:
                return nested_text

    if best_html:
        return best_html
    if best_plain:
        return best_plain

    return ""

def _clean_text(text: str) -> str:
    """Remove common newsletter boilerplate and excessive whitespace."""
    import re, html as htmlmod
    if not text:
        return text
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    boilerplate = re.compile(
        r"(unsubscribe|email preferences|manage preferences|update profile|"
        r"support|privacy|sponsorship|sponsor|view this issue|view this|"
        r"view online|open in browser)",
        re.I,
    )
    for raw in t.split("\n"):
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        # Drop single-word labels and obvious noise
        if line.lower() in {"pen", "video", "sponsored", "sponsor"}:
            continue
        if boilerplate.search(line):
            continue
        # Drop link-only lines and isolated punctuation arrows
        if line.startswith("http") or line in {"›", "»", ">", "|"}:
            continue
        # Drop short numeric or symbol-only lines (e.g., "96")
        if re.fullmatch(r"[0-9]{1,4}", line):
            continue
        if len(line) < 3 and not any(c.isalpha() for c in line):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return htmlmod.unescape(cleaned)

def _strip_leading_subject(text: str, subject: str) -> str:
    """Remove duplicated subject heading at top of body if present.
    Handles cases where the subject has newsletter tags like [Brand] Title,
    while the first line in the body is just 'Title'."""
    import re
    if not text or not subject:
        return text

    def normalize(s: str, *, lax: bool = False) -> str:
        s = (s or "")
        s = re.sub(r"\s+", " ", s).strip()
        s = s.strip('"\''"[](){}")
        s = s.lower()
        if lax:
            s = re.sub(r"[^a-z0-9]+", " ", s).strip()
        return s

    def strip_tags(s: str) -> str:
        # remove leading [xxx] segments and common prefixes like re:/fwd:
        s = re.sub(r"^\s*(re|fw|fwd)\s*:\s*", "", s, flags=re.I)
        s = re.sub(r"\[[^\]]+\]\s*", "", s).strip()
        return s

    # Build subject variants
    base = subject
    no_tags = strip_tags(base)
    variants = {
        normalize(base),
        normalize(no_tags),
        normalize(base, lax=True),
        normalize(no_tags, lax=True),
    }

    lines = text.splitlines()
    # find first non-empty line and maybe the next one
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return text

    def line_matches(idx: int) -> bool:
        ln = normalize(lines[idx])
        ln_lax = normalize(lines[idx], lax=True)
        return (ln in variants) or (ln_lax in variants)

    drop = 0
    if line_matches(i):
        drop = 1
        # sometimes newsletters repeat the subject twice
        if i + 1 < len(lines) and line_matches(i + 1):
            drop = 2

    if drop:
        kept = lines[:i] + lines[i + drop:]
        return "\n".join(kept).lstrip("\n")
    return text

def get_thread_detail(user_id: str, thread_id: str) -> str:
    """
    Return JSON with details for the selected email/thread:
    {
      "success": true,
      "subject": "...",
      "from": "...",
      "date": "...",
      "body": "plain text body"
    }
    """
    try:
        svc = get_gmail_service(user_id)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

    # Try as message first for convenience
    try:
        msg = (
            svc.users()
            .messages()
            .get(userId="me", id=thread_id, format="full")
            .execute()
        )
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        header_map = {h["name"].lower(): h["value"] for h in headers}
        subject = header_map.get("subject", "(No subject)")
        sender = header_map.get("from", "")
        date = header_map.get("date", "")
        body = _clean_text(_extract_plain_text(payload).strip())
        body = _strip_leading_subject(body, subject)
        return json.dumps({"success": True, "subject": subject, "from": sender, "date": date, "body": body})
    except Exception:
        # Fallback to thread; use the last message in the thread
        try:
            th = (
                svc.users()
                .threads()
                .get(userId="me", id=thread_id, format="full")
                .execute()
            )
            messages = th.get("messages", [])
            if not messages:
                return json.dumps({"success": False, "error": "Thread has no messages"})
            last = messages[-1]
            payload = last.get("payload", {})
            headers = payload.get("headers", [])
            header_map = {h["name"].lower(): h["value"] for h in headers}
            subject = header_map.get("subject", "(No subject)")
            sender = header_map.get("from", "")
            date = header_map.get("date", "")
            body = _clean_text(_extract_plain_text(payload).strip())
            body = _strip_leading_subject(body, subject)
            return json.dumps({"success": True, "subject": subject, "from": sender, "date": date, "body": body})
        except Exception as e2:
            return json.dumps({"success": False, "error": str(e2)})


