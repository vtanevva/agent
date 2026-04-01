# backend/services/slack_text.py

import hashlib
import re

IGNORED_SUBTYPES = {
    "bot_message",
    "channel_join",
    "channel_leave",
    "message_changed",
    "message_deleted",
    "thread_broadcast",
}

ALLOWED_EVENT_TYPES = {
    "app_mention",
    "message",
}

ACTION_HINTS = [
    "can you",
    "can u",
    "please",
    "send",
    "take",
    "prepare",
    "do this",
    "follow up",
    "reply to",
    "book",
    "schedule",
    "make sure",
    "remind",
    "create task",
    "check",
    "review",
    "call",
    "email",
]


def extract_payload_parts(payload: dict):
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    container = payload.get("container") if isinstance(payload.get("container"), dict) else {}
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    return event, container, message


def extract_text(payload: dict, event: dict, message: dict) -> str:
    # 1) Normal text fields
    text = (
        (payload.get("text") or "")
        or (event.get("text") or "")
        or (message.get("text") or "")
    ).strip()

    if text:
        return text

    # 2) Blocks fallback
    blocks = event.get("blocks") or payload.get("blocks") or []
    block_texts = []

    for block in blocks:
        if not isinstance(block, dict):
            continue

        txt = block.get("text")
        if isinstance(txt, dict):
            t = txt.get("text")
            if t:
                block_texts.append(t)

        for el in block.get("elements", []):
            if isinstance(el, dict):
                inner_elements = el.get("elements", [])
                if isinstance(inner_elements, list):
                    for sub in inner_elements:
                        if isinstance(sub, dict):
                            t = sub.get("text")
                            if t:
                                block_texts.append(t)

    if block_texts:
        return "\n".join(block_texts).strip()

    # 3) Attachments fallback
    attachments = event.get("attachments") or payload.get("attachments") or []
    attachment_texts = []

    for att in attachments:
        if not isinstance(att, dict):
            continue
        for key in ("text", "fallback", "title", "pretext"):
            val = att.get(key)
            if val:
                attachment_texts.append(str(val))

    if attachment_texts:
        return "\n".join(attachment_texts).strip()

    return ""

def extract_channel(payload: dict, event: dict, container: dict) -> str:
    return (
        (payload.get("channel") or "")
        or (payload.get("channel_id") or "")
        or (event.get("channel") or "")
        or (event.get("channel_id") or "")
        or (container.get("channel_id") or "")
    ).strip()


def extract_ts(payload: dict, event: dict) -> str:
    return (
        str(payload.get("ts") or "")
        or str(payload.get("message_ts") or "")
        or str(event.get("ts") or "")
        or str(event.get("event_ts") or "")
        or str(payload.get("event_ts") or "")
    ).strip()


def extract_user(payload: dict, event: dict) -> tuple[str, str]:
    user_id = (
        (payload.get("user_id") or "")
        or (event.get("user") or "")
        or (payload.get("user") or "")
    ).strip()
    user = (payload.get("user") or user_id or "").strip()
    return user, user_id


def clean_text(text: str) -> str:
    text = re.sub(r"^<@[\w]+>\s*", "", text).strip()
    return text


def prepare_text_for_classification(text: str) -> str:
    """
    Removes forwarded / quoted Slack transcript noise before classification.
    Example:
    can u take me my earring
    [March 15th, 2026 8:28 PM] vanesa.taneva12: ...
    """
    if not text:
        return ""

    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        # Stop when a quoted transcript starts
        if stripped.startswith("[") and "]" in stripped and ":" in stripped:
            break

        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()

    if not cleaned:
        cleaned = text.strip()

    return cleaned


def looks_like_action(text: str) -> bool:
    lower = text.lower().strip()
    return any(hint in lower for hint in ACTION_HINTS)


def should_ignore_event(event: dict, clean_text_value: str) -> tuple[bool, str]:
    event_type = event.get("type")
    subtype = event.get("subtype")
    channel_type = event.get("channel_type", "")

    if event_type and event_type not in ALLOWED_EVENT_TYPES:
        return True, f"unsupported_event_type:{event_type}"

    if event.get("bot_id"):
        return True, "bot_message"

    if subtype in IGNORED_SUBTYPES:
        return True, f"ignored_subtype:{subtype}"

    if not clean_text_value:
        return True, "empty_text"

    if event_type == "app_mention":
        return False, ""

    if event_type == "message":
        if channel_type in {"im", "app_home", "channel", "group"}:
            return False, ""

    return True, f"unhandled_context:event_type={event_type},channel_type={channel_type}"


def build_fallback_source_id(channel: str, user_id: str, clean_text_value: str) -> str:
    raw = f"{channel}|{user_id}|{clean_text_value.lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"fallback:{digest}"
