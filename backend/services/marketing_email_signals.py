"""
Heuristics to avoid promoting bulk marketing / newsletters into Grafik tasks.

Uses RFC-style headers when present (Gmail Pub/Sub path) and conservative
body/subject cues when headers are missing (manual /ingest/gmail).
"""

from __future__ import annotations

import re
from typing import Any

_RE_SUBJECT_PROMO = re.compile(
    r"(?i)\b(newsletter|weekly digest|daily digest|flash sale|black friday|"
    r"cyber monday|limited time|\d+\s*%\s*off|exclusive offer|special offer|"
    r"promo(tion)? code|deal of the day|shop now|order today)\b"
)

_RE_BODY_VENDOR_FOOTER = re.compile(
    r"(?i)(mailchimp|constant\s+contact|sendinblue|brevo|campaign\s+monitor|"
    r"hubspot\s+email|sendgrid|customer\.io|klaviyo|beehiiv|substack)"
)

_RE_BODY_UNSUB_PAIR = re.compile(
    r"(?is)unsubscribe.{0,200}(view\s+in\s+your\s+browser|view\s+this\s+email\s+in\s+your\s+browser)|"
    r"(view\s+in\s+your\s+browser|view\s+this\s+email\s+in\s+your\s+browser).{0,200}unsubscribe"
)


def _header_map_from_payload(payload: dict[str, Any] | None) -> dict[str, str]:
    """
    Normalize headers to lower-cased keys for lookup.
    Supports:
      - payload['headers'] as dict name -> value
      - payload['headers'] as list of {name, value}
    """
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("headers")
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k is None:
                continue
            key = str(k).strip().lower()
            if key:
                out[key] = str(v or "").strip()
        return out
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("Name") or "").strip()
            if not name:
                continue
            out[name.lower()] = str(item.get("value") or item.get("Value") or "").strip()
        return out
    return out


def _get_header(headers: dict[str, str], name: str) -> str:
    return str(headers.get(name.lower()) or "").strip()


def is_likely_marketing_or_newsletter(
    *,
    payload: dict[str, Any] | None,
    subject: str,
    raw_text: str,
) -> bool:
    """
    Return True when the message is very likely bulk marketing / newsletter traffic.

    Intentionally conservative on single strong signals that also appear on legitimate
    transactional mail (e.g. List-Unsubscribe alone on GitHub notifications).
    """
    headers = _header_map_from_payload(payload)
    subj = (subject or "").strip()
    body = (raw_text or "").strip()
    combined = f"{subj}\n{body}"[:8000]

    precedence = _get_header(headers, "Precedence").lower()
    if precedence == "bulk":
        return True

    auto_sub = _get_header(headers, "Auto-Submitted").lower()
    if auto_sub.startswith("auto-generated"):
        return True

    list_unsub = _get_header(headers, "List-Unsubscribe")
    list_id = _get_header(headers, "List-Id")

    if list_unsub and _RE_SUBJECT_PROMO.search(subj):
        return True

    if list_unsub and list_id and _RE_BODY_UNSUB_PAIR.search(combined):
        return True

    if list_unsub and _RE_BODY_VENDOR_FOOTER.search(combined):
        return True

    if _RE_BODY_VENDOR_FOOTER.search(combined) and _RE_SUBJECT_PROMO.search(subj):
        return True

    return False
