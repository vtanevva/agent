from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Tuple


def _b64url_decode(data: str) -> bytes:
    s = (data or "").strip()
    if not s:
        return b""
    # Pad to multiple of 4
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def get_header(headers: List[Dict[str, Any]], name: str) -> str:
    target = (name or "").strip().lower()
    for h in headers or []:
        if str(h.get("name", "")).strip().lower() == target:
            return str(h.get("value") or "")
    return ""


def extract_plain_text(payload: Dict[str, Any]) -> str:
    """
    Best-effort extraction of text/plain from a Gmail message payload.
    """
    if not isinstance(payload, dict):
        return ""

    mime_type = str(payload.get("mimeType") or "")
    body = payload.get("body") or {}
    data = body.get("data")
    if mime_type.startswith("text/plain") and data:
        try:
            return _b64url_decode(str(data)).decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    # Some messages have body.data at top-level even if mimeType is multipart/alternative
    if data and isinstance(data, str) and not payload.get("parts"):
        try:
            return _b64url_decode(data).decode("utf-8", errors="replace").strip()
        except Exception:
            pass

    # Recurse parts
    parts = payload.get("parts") or []
    if isinstance(parts, list):
        # Prefer text/plain first
        for p in parts:
            txt = extract_plain_text(p)
            if txt:
                return txt
        # Fallback: try html as last resort by stripping tags lightly
        for p in parts:
            mt = str((p or {}).get("mimeType") or "")
            if mt.startswith("text/html"):
                html = ""
                try:
                    html_data = ((p or {}).get("body") or {}).get("data")
                    if html_data:
                        html = _b64url_decode(str(html_data)).decode("utf-8", errors="replace")
                except Exception:
                    html = ""
                if html:
                    return _strip_html(html).strip()
    return ""


def _strip_html(html: str) -> str:
    # Minimal, dependency-free tag stripping (good enough for classification).
    import re

    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    s = re.sub(r"(?is)<br\s*/?>", "\n", s)
    s = re.sub(r"(?is)</p\s*>", "\n\n", s)
    s = re.sub(r"(?is)<.*?>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&lt;", "<", s)
    s = re.sub(r"&gt;", ">", s)
    s = re.sub(r"\s+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s

