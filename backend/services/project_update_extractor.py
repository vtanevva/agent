import re
from typing import Any


_RE_BLOCKER = re.compile(
    r"\b(blocker|blocked by|blocked on|still waiting|still waiting for|waiting for|waiting on|still pending|pending approval|pending review|stuck on|held up by)\b",
    re.IGNORECASE,
)

_RE_STATUS = re.compile(
    r"\b(in progress|ongoing|underway|completed|done|finished|still working on|working on|reviewing|drafting|finalizing)\b",
    re.IGNORECASE,
)

_RE_NEXT_STEP = re.compile(
    r"\b(next step|next steps|i will|we will|going to|plan to|will send|will share|will review|will finalize)\b",
    re.IGNORECASE,
)

_RE_PRIORITY = re.compile(
    r"\b(priority|priorities|focus this week|focusing on|top priority|currently prioritizing)\b",
    re.IGNORECASE,
)

_RE_STATUS_LABELS_ONLY = re.compile(
    r"\b(status|update|fyi)\s*[:\-]",
    re.IGNORECASE,
)

_RE_WRAPPER_PREFIX = re.compile(
    r"^\s*(subject|body|update|fyi|note|status|blocker|blockers|next step|next steps|priorities|priority)\s*:\s*",
    re.IGNORECASE,
)

_RE_GMAIL_SUBJECT_BODY = re.compile(
    r"^\s*subject\s*:\s*(?P<subject>.*?)\s+body\s*:\s*(?P<body>.+)\s*$",
    re.IGNORECASE,
)

_BAD_VALUES = {"unknown", "n/a", "na", "none", "null", "nil"}


def _clean(text: str) -> str:
    return " ".join((text or "").strip().split())

def _strip_wrappers(text: str) -> dict[str, str]:
    """
    Normalizes Slack/Gmail formatted text into components.
    Returns { "subject": ..., "body": ..., "text": ... } (any may be "").
    """
    t = _clean(text)
    if not t:
        return {"subject": "", "body": "", "text": ""}

    m = _RE_GMAIL_SUBJECT_BODY.match(t)
    if m:
        subject = _clean(m.group("subject") or "")
        body = _clean(m.group("body") or "")
        return {"subject": subject, "body": body, "text": body or subject}

    # Single prefix stripping (Slack "Update: ..." etc)
    t2 = _RE_WRAPPER_PREFIX.sub("", t)
    if t2 != t:
        t2 = _clean(t2)
    return {"subject": "", "body": "", "text": t2}


def _is_useful_value(value: str) -> bool:
    v = _clean(value)
    if not v:
        return False
    if v.lower() in _BAD_VALUES:
        return False
    # avoid returning naked wrappers
    if v.lower() in {"update", "status", "fyi", "note"}:
        return False
    return True


def _sentences(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    # Split on ., ;, or line breaks. Keep question marks/exclamation as sentence end too.
    parts = re.split(r"(?<=[\.\?\!;])\s+|\n+", t)
    out: list[str] = []
    for p in parts:
        s = _clean(p)
        s = _RE_WRAPPER_PREFIX.sub("", s).strip()
        s = _clean(s)
        if _is_useful_value(s):
            out.append(s)
    return out


def _pick_best(sentences: list[str], pattern: re.Pattern[str], *, label_prefixes: tuple[str, ...] = ()) -> str | None:
    """
    Pick a single best sentence for a field, preferring those that look like explicit labels.
    """
    best = None
    for s in sentences:
        if not pattern.search(s):
            continue
        if label_prefixes and any(s.lower().startswith(p) for p in label_prefixes):
            return s
        best = best or s
    return best


def _extract_after_keyword(text: str, keywords: tuple[str, ...]) -> str | None:
    """
    Extracts the clause after a keyword label like 'Top priority ...' or 'Priorities: ...'.
    Falls back to None if extraction isn't clear.
    """
    t = _clean(text)
    lower = t.lower()
    for kw in keywords:
        idx = lower.find(kw)
        if idx == -1:
            continue
        tail = t[idx + len(kw):].lstrip(" :-").strip()
        tail = _clean(tail)
        if _is_useful_value(tail):
            return tail
    return None


def extract_project_updates(text: str) -> dict[str, Any]:
    """
    Extract candidate project context updates from a raw message.
    LOG ONLY for now. Do not auto-save yet.
    """
    parts = _strip_wrappers(text)
    clean_text = parts["text"]

    if not clean_text:
        return {
            "has_project_update": False,
            "fields": {},
            "confidence": 0.0,
            "reason": "empty_text",
        }

    # Prefer extracting from the body-like portion; subject is low-signal.
    raw_for_extract = clean_text
    sentences = _sentences(raw_for_extract)
    if not sentences:
        sentences = [raw_for_extract]

    fields: dict[str, str] = {}
    confidence = 0.0

    blocker = _pick_best(sentences, _RE_BLOCKER, label_prefixes=("blocker", "blocked"))
    if blocker:
        fields["blockers"] = blocker
        confidence = max(confidence, 0.82)

    next_steps = _pick_best(sentences, _RE_NEXT_STEP, label_prefixes=("next step", "next steps"))
    if next_steps:
        fields["next_steps"] = next_steps
        confidence = max(confidence, 0.78)

    priorities = None
    for s in sentences:
        if not _RE_PRIORITY.search(s):
            continue
        extracted = _extract_after_keyword(
            s,
            (
                "top priority",
                "priorities",
                "priority",
                "focus this week",
                "focusing on",
                "currently prioritizing",
            ),
        )
        priorities = extracted or s
        break
    if priorities and _is_useful_value(priorities):
        fields["current_priorities"] = priorities
        confidence = max(confidence, 0.76)

    status = _pick_best(sentences, _RE_STATUS, label_prefixes=("status",))
    if status:
        # Don't treat pure priority phrasing as status, even if it contains words like "finalizing".
        if _RE_PRIORITY.search(status) and not _RE_STATUS_LABELS_ONLY.search(status):
            status = None

    if status:
        fields["current_status"] = status
        confidence = max(confidence, 0.72)

    # Avoid filling multiple fields with the exact same generic sentence unless it's the only signal.
    # If status and priorities are identical, prefer priorities if it has priority keywords,
    # otherwise keep status and drop priorities.
    if (
        fields.get("current_status")
        and fields.get("current_priorities")
        and fields["current_status"] == fields["current_priorities"]
    ):
        if _RE_PRIORITY.search(fields["current_priorities"]):
            fields.pop("current_status", None)
        else:
            fields.pop("current_priorities", None)

    has_project_update = len(fields) > 0

    return {
        "has_project_update": has_project_update,
        "fields": fields,
        "confidence": confidence if has_project_update else 0.0,
        "reason": "matched_patterns" if has_project_update else "no_match",
    }