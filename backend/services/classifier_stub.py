import re

ACTION_HINTS = [
    r"\bplease\b",
    r"\bneed\b",
    r"\btodo\b", r"\bto-do\b",
    r"\baction\b",
    r"\bdeadline\b",
    r"\basap\b", r"\burgent\b",
    r"\bfollow up\b",
    r"\bbook\b",
    r"\bschedule\b",
    r"\bcreate\b",
    r"\bfix\b",
    r"\bupdate\b",
]

REPLY_HINTS = [
    r"\bcan you\b",
    r"\bcould you\b",
    r"\bwhat do you think\b",
    r"\bthoughts\b",
    r"\bcan you confirm\b",
    r"\blet me know\b",
    r"\bpls advise\b",
    r"\bquestion\b",
]

def classify(text: str) -> dict:
    t = (text or "").strip()
    if not t:
        return {"type": "INFO", "title": None, "summary": "Empty message.", "confidence": 0.9}

    lower = t.lower()

    # ✅ REPLY FIRST (questions / confirmations)
    if lower.endswith("?") or any(re.search(p, lower) for p in REPLY_HINTS):
        summary = t[:200] + ("..." if len(t) > 200 else "")
        return {
            "type": "REPLY",
            "title": None,
            "summary": summary,
            "suggested_reply": "Got it — I’ll confirm and get back to you shortly.",
            "confidence": 0.65,
        }

    # ✅ ACTION SECOND (task requests)
    if any(re.search(p, lower) for p in ACTION_HINTS):
        title = t[:60]
        summary = t[:200] + ("..." if len(t) > 200 else "")
        return {"type": "ACTION", "title": title, "summary": summary, "confidence": 0.65}

    return {"type": "INFO", "title": None, "summary": t[:200], "confidence": 0.55}