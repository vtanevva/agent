"""Gmail style analysis and reply draft generation tools."""

import os
import json
from typing import Dict, List, Optional

from dotenv import load_dotenv
import openai
from googleapiclient.discovery import build

# Tool registry removed - agents call functions directly now
from app.utils.tool_registry import register, ToolSchema
from app.utils import oauth_utils
from app.utils.google_api_helpers import get_gmail_service

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def _extract_plain_text(payload: Dict) -> str:
    """Recursively prefer text/plain; fallback to stripped text/html."""
    if not payload:
        return ""

    def decode_body(body: Dict) -> str:
        data = (body or {}).get("data")
        if not data:
            return ""
        try:
            import base64
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    # HTML stripper + entity handling
    import re, html as htmlmod
    def strip_html(html: str) -> str:
        text = re.sub(r"(?i)<br\s*/?>", "\n", html)
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", "", text)
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", "", text)
        text = re.sub(r"(?s)<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return htmlmod.unescape(text).strip()

    mime = (payload.get("mimeType") or "").lower()
    # If not multipart, consider direct body; otherwise prefer parts
    if not mime.startswith("multipart/"):
        direct = decode_body(payload.get("body", {}))
        if direct and (len(direct.strip()) >= 8 or any(c.isalpha() for c in direct)):
            if mime.startswith("text/html"):
                return strip_html(direct)
            return direct

    def is_meaningful(text: str) -> bool:
        if not text:
            return False
        s = text.strip()
        return (len(s) >= 8) and any(ch.isalpha() for ch in s)

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
        nested = _extract_plain_text(p)
        if nested:
            return nested

    # Fallback to HTML stripped
    for p in parts:
        mt = (p.get("mimeType") or "").lower()
        if mt.startswith("text/html"):
            html = decode_body(p.get("body", {}))
            if html:
                stripped = strip_html(html)
                if is_meaningful(stripped):
                    return stripped
        if p.get("parts"):
            nested_text = _extract_plain_text({"parts": p.get("parts")})
            if nested_text:
                return nested_text
    if best_html:
        return best_html
    if best_plain:
        return best_plain
    return ""


def _fetch_recent_sent_texts(user_id: str, max_samples: int = 10) -> List[str]:
    svc = get_gmail_service(user_id)
    resp = svc.users().messages().list(
        userId="me",
        q="in:sent -from:mailer-daemon@googlemail.com",
        maxResults=max_samples * 2,  # fetch extra to filter empty
    ).execute()
    messages = resp.get("messages", [])
    samples: List[str] = []
    for m in messages:
        msg = (
            svc.users()
            .messages()
            .get(userId="me", id=m["id"], format="full")
            .execute()
        )
        text = _extract_plain_text(msg.get("payload", {})).strip()
        if text:
            samples.append(text)
        if len(samples) >= max_samples:
            break
    return samples


def analyze_email_style(user_id: str, max_samples: int = 10) -> str:
    """Analyze user's writing style from recent Sent emails. Returns JSON profile."""
    try:
        samples = _fetch_recent_sent_texts(user_id, max_samples=max_samples)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
    if not samples:
        return json.dumps({"success": False, "error": "No sent emails found to analyze."})
    joined = "\n\n---\n\n".join(samples[:max_samples])
    prompt = (
        "Analyze the user's writing style from the following email samples.\n"
        "Return a concise JSON object with these fields:\n"
        "{\n"
        '  "tone": "concise/warm/professional/... (short string)",\n'
        '  "formality": "informal/semi-formal/formal",\n'
        '  "greeting_style": "e.g., Hi {name}, Hello {name}, no greeting",\n'
        '  "closing_style": "e.g., Best regards, Thanks, etc.",\n'
        '  "signature_pattern": "short description of signature if any",\n'
        '  "length_preference": "short/medium/long",\n'
        '  "punctuation_caps": "notes on punctuation/capitalization quirks",\n'
        '  "common_phrases": ["array","of","phrases"],\n'
        '  "guidelines": ["bullet points for how to emulate the style"]\n'
        "}\n"
        "Only output valid JSON with double quotes and no commentary.\n\n"
        f"EMAIL SAMPLES:\n{joined}"
    )
    try:
        resp = openai.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        content = resp.choices[0].message.content or "{}"
        # Validate JSON
        profile = json.loads(content)
        return json.dumps({"success": True, "profile": profile})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def _fetch_thread_context(user_id: str, thread_id: str) -> Dict[str, str]:
    """Fetch subject and a plain-text body/snippet from the referenced thread/message."""
    svc = get_gmail_service(user_id)
    # Try as message first; if not found, try as thread
    subject = "(No subject)"
    context_text = ""
    # local cleaner mirrors gmail_detail
    def _clean_text_local(text: str) -> str:
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
            if line.lower() in {"pen", "video", "sponsored", "sponsor"}:
                continue
            if boilerplate.search(line):
                continue
            if line.startswith("http") or line in {"›", "»", ">", "|"}:
                continue
            if re.fullmatch(r"[0-9]{1,4}", line):
                continue
            if len(line) < 3 and not any(c.isalpha() for c in line):
                continue
            lines.append(line)
        cleaned = "\n".join(lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return htmlmod.unescape(cleaned)
    def _strip_leading_subject_local(text: str, subj: str) -> str:
        import re
        if not text or not subj:
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
            s = re.sub(r"^\s*(re|fw|fwd)\s*:\s*", "", s, flags=re.I)
            s = re.sub(r"\[[^\]]+\]\s*", "", s).strip()
            return s
        base = subj
        no_tags = strip_tags(base)
        variants = {
            normalize(base),
            normalize(no_tags),
            normalize(base, lax=True),
            normalize(no_tags, lax=True),
        }
        lines = text.splitlines()
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
            if i + 1 < len(lines) and line_matches(i + 1):
                drop = 2
        if drop:
            kept = lines[:i] + lines[i + drop :]
            return "\n".join(kept).lstrip("\n")
        return text
    try:
        msg = (
            svc.users()
            .messages()
            .get(userId="me", id=thread_id, format="full")
            .execute()
        )
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        for h in headers:
            if h.get("name") == "Subject":
                subject = h.get("value", subject)
                break
        body = _extract_plain_text(payload)
        context_text = _clean_text_local((body or msg.get("snippet", "")))
        context_text = _strip_leading_subject_local(context_text, subject)[:2000]
        return {"subject": subject, "context": context_text}
    except Exception:
        # Fallback to thread
        th = (
            svc.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute()
        )
        msgs = th.get("messages", [])
        if msgs:
            last = msgs[-1]
            payload = last.get("payload", {})
            headers = payload.get("headers", [])
            for h in headers:
                if h.get("name") == "Subject":
                    subject = h.get("value", subject)
                    break
            body = _extract_plain_text(payload)
            context_text = _clean_text_local((body or last.get("snippet", "")))
            context_text = _strip_leading_subject_local(context_text, subject)[:2000]
        return {"subject": subject, "context": context_text}


def generate_reply_draft(
    user_id: str,
    thread_id: str,
    to: str,
    user_points: Optional[str] = None,
    max_samples: int = 10,
) -> str:
    """Generate a reply draft for a given thread, emulating the user's style."""
    # Style
    style_raw = analyze_email_style(user_id=user_id, max_samples=max_samples)
    try:
        style_data = json.loads(style_raw)
        style_profile = style_data.get("profile", {})
    except Exception:
        style_profile = {}
    # Context
    try:
        ctx = _fetch_thread_context(user_id, thread_id)
    except Exception as e:
        return json.dumps({"success": False, "error": f"Failed to load thread: {e}"})

    sys = "You are an assistant that drafts Gmail replies in the user's personal style."
    style_desc = json.dumps(style_profile, ensure_ascii=False)
    user_points = user_points or ""
    prompt = (
        f"Subject: {ctx.get('subject','(No subject)')}\n"
        f"Last message snippet (from them): {ctx.get('context','')}\n\n"
        f"User style profile (JSON): {style_desc}\n\n"
        f"User's points to include (optional): {user_points}\n\n"
        "Write a direct reply email body from ME to THEM that matches the user's style.\n"
        "- DO NOT quote, restate, or paraphrase the sender's text.\n"
        "- Produce NEW content that acknowledges key points and moves the conversation forward.\n"
        "- Answer requests/questions and propose a clear next step when appropriate.\n"
        "- Avoid meta phrases like 'you said' or 'as mentioned'.\n"
        "- No subject line; body only. Keep 2–6 sentences. Include greeting/closing if appropriate."
    )
    try:
        resp = openai.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": prompt}],
            temperature=0.2,
        )
        body = resp.choices[0].message.content or ""
        return json.dumps({"success": True, "to": to, "thread_id": thread_id, "body": body})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


# Register tools
register(
    analyze_email_style,
    ToolSchema(
        name="analyze_email_style",
        description="Analyze user's writing style from recent Sent emails and return a JSON profile.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "max_samples": {"type": "integer", "minimum": 3, "maximum": 30},
            },
            "required": ["user_id"],
        },
    ),
)

register(
    generate_reply_draft,
    ToolSchema(
        name="generate_reply_draft",
        description="Generate a reply draft for a thread, emulating user's style.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "to": {"type": "string"},
                "user_points": {"type": "string"},
                "max_samples": {"type": "integer", "minimum": 3, "maximum": 30},
            },
            "required": ["user_id", "thread_id", "to"],
        },
    ),
)


