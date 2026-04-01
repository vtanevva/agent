import hashlib
import re


def extract_gmail_fields(payload: dict) -> dict:
    return {
        "message_id": (payload.get("message_id") or "").strip(),
        "thread_id": (payload.get("thread_id") or "").strip(),
        "sender": (payload.get("from") or payload.get("sender") or "").strip(),
        "recipient": (payload.get("to") or payload.get("recipient") or "").strip(),
        "subject": (payload.get("subject") or "").strip(),
        "body": (payload.get("body") or payload.get("text") or "").strip(),
        "timestamp": (payload.get("timestamp") or payload.get("internal_date") or "").strip(),
    }


def clean_email_text(subject: str, body: str) -> str:
    raw = f"{subject}\n\n{body}".strip()
    raw = re.sub(r"\s+", " ", raw)

    raw = re.sub(r"On\s.+?wrote:", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"From:\s.+", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"Sent:\s.+", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"To:\s.+", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"Subject:\s.+", "", raw, flags=re.IGNORECASE)

    return raw.strip()


def prepare_email_for_classification(subject: str, body: str) -> str:
    subject = (subject or "").strip()
    body = (body or "").strip()

    combined = f"Subject: {subject}\nBody: {body}".strip()
    combined = re.sub(r"\s+", " ", combined)

    return combined[:4000].strip()


def build_gmail_source_id(message_id: str, thread_id: str, sender: str, subject: str) -> str:
    if message_id:
        return f"gmail:{message_id}"

    fallback_raw = f"{thread_id}|{sender}|{subject}"
    digest = hashlib.sha256(fallback_raw.encode("utf-8")).hexdigest()[:16]
    return f"gmail:fallback:{digest}"