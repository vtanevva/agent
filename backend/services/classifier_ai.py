import json
import os
import re
from typing import Any, Dict, Optional

from openai import OpenAI


# --------- Config ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

ALLOWED_REPLY_TYPES = {"none", "short", "time_relevant", "context_relevant"}

client: Optional[OpenAI] = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)


# --------- Heuristic patterns ----------
_IMPERATIVE_VERBS = (
    "send",
    "create",
    "complete",
    "finish",
    "prepare",
    "draft",
    "review",
    "handle",
    "take care of",
    "look into",
    "write",
    "book",
    "make sure",
    "ensure",
    "verify",
    "check",
    "review",
    "confirm",
    "approve",
    "reject",
    "complete",
    "schedule",
    "fix",
    "update",
    "follow up",
    "remind",
    "call",
    "email",
    "text",
    "submit",
    "confirm",
    "arrange",
)

_VERB_PATTERN = r"(?:%s)" % "|".join(re.escape(v) for v in _IMPERATIVE_VERBS)

_RE_GREETING_PREFIX = re.compile(
    r"^\s*(hi|hey|hello|good morning|good afternoon|good evening)\b(?:\s+there)?[\s\.\!\,]*",
    re.IGNORECASE,
)

_RE_QUESTION = re.compile(r"\?\s*$")
_RE_QUESTION_WORD = re.compile(r"^\s*(what|when|where|why|how|who)\b", re.IGNORECASE)

_RE_TIME_SIGNAL = re.compile(
    r"\b(today|tomorrow|tonight|asap|urgent|by\s+\w+|by\s+\d{1,2}|\d{1,2}:\d{2}|deadline|friday|monday|tuesday|wednesday|thursday|saturday|sunday)\b",
    re.IGNORECASE,
)

_RE_REPLY_EXPECTED = re.compile(
    r"\b(let me know|please confirm|please reply|please advise|what do you think|looking forward to your feedback|i look forward to your feedback)\b",
    re.IGNORECASE,
)

_RE_STATUS_UPDATE = re.compile(
    r"(?:\b(still pending|still waiting|waiting for|waiting on|blocked by|quick update|for your information|fyi|next step|reminder|everything is now in place|regarding the task)\b|\bupdate\s*[:\-])",
    re.IGNORECASE,
)

_RE_SUGGESTION_NOT_REQUEST = re.compile(
    r"^\s*(we should|we need to|it would be good to|it would be great if)\b",
    re.IGNORECASE,
)

# Confirmation/status-check questions that should not create tasks
_RE_CONFIRM_STATUS_CHECK = re.compile(
    r"\b(?:can|could|would)\s+you\s+confirm\b.*\b(whether|if|that)\b",
    re.IGNORECASE,
)

# Strong request patterns
_RE_CAN_YOU_REQUEST = re.compile(
    rf"\b(?:can|could|would)\s+you\b.*?\b{_VERB_PATTERN}\b",
    re.IGNORECASE,
)

_RE_PLEASE_REQUEST = re.compile(
    rf"\bplease\b.*?\b{_VERB_PATTERN}\b",
    re.IGNORECASE,
)

_RE_DIRECT_REQUEST = re.compile(
    rf"^\s*\b{_VERB_PATTERN}\b(?:\s+this|\s+that|\s+it|\s+the|\s+my|\s+our|\s+by\b|\s+before\b|\s+for\b|\s+to\b|$)",
    re.IGNORECASE,
)


def _mk_summary(text: str) -> str:
    t = (text or "").strip()
    return (t[:400] + ("..." if len(t) > 400 else "")) if t else "Empty message."


def _normalize_for_heuristics(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^\s*subject:\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\bbody:\s*", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _mk_title(text: str) -> str:
    t = " ".join(((text or "").strip()).split())
    if not t:
        return "Message"
    t = t.strip().rstrip(".!?")
    return (t[:120] + ("..." if len(t) > 120 else "")) if len(t) > 120 else t[:120]


def _looks_like_action_request(text: str) -> bool:
    t = _normalize_for_heuristics(text)

    if not t:
        return False

    if _RE_CAN_YOU_REQUEST.search(t):
        return True

    if _RE_PLEASE_REQUEST.search(t):
        return True

    if _RE_DIRECT_REQUEST.search(t):
        return True

    return False


def _strong_override_action_request(text: str) -> bool:
    """
    Stricter gate for overrides that would flip has_action.

    Only treat as strong enough to override when the raw text includes:
    - can/could/would you + verb
    - please + verb
    - strong imperative at sentence start
    """
    t = _normalize_for_heuristics(text)
    if not t:
        return False
    # Confirmation/status-check questions should not be treated as "strong requests"
    # for task creation overrides.
    if _RE_CONFIRM_STATUS_CHECK.search(t):
        return False
    return bool(
        _RE_CAN_YOU_REQUEST.search(t)
        or _RE_PLEASE_REQUEST.search(t)
        or _RE_DIRECT_REQUEST.search(t)
    )


def _heuristic_classify(text: str) -> Optional[Dict[str, Any]]:
    """
    Return a classification dict when intent is very clear, else None.

    IMPORTANT:
    This function should only receive RAW message text.
    """
    t = _normalize_for_heuristics(text)
    if not t:
        return {
            "has_action": False,
            "reply_type": "none",
            "title": None,
            "summary": "Empty message.",
            "suggested_reply": None,
            "confidence": 0.9,
        }

    m = _RE_GREETING_PREFIX.match(t)
    if m:
        remainder = t[m.end():].strip()
        if not remainder:
            return {
                "has_action": False,
                "reply_type": "short",
                "title": "Greeting",
                "summary": _mk_summary(t),
                "suggested_reply": "Hey! What can I help with?",
                "confidence": 0.8,
            }

    if _RE_CONFIRM_STATUS_CHECK.search(t):
        reply_type = "time_relevant" if _RE_TIME_SIGNAL.search(t) else "context_relevant"
        return {
            "has_action": False,
            "reply_type": reply_type,
            "title": "Question",
            "summary": _mk_summary(t),
            "suggested_reply": "Got it — I’ll confirm and get back to you shortly.",
            "confidence": 0.76,
        }

    has_action = _looks_like_action_request(t)
    has_time_signal = bool(_RE_TIME_SIGNAL.search(t))
    expects_reply = bool(_RE_REPLY_EXPECTED.search(t))
    is_status_update = bool(_RE_STATUS_UPDATE.search(t))
    is_question = bool(_RE_QUESTION.search(t) or _RE_QUESTION_WORD.search(t))
    is_suggestion = bool(_RE_SUGGESTION_NOT_REQUEST.search(t))

    if has_action:
        if has_time_signal:
            reply_type = "time_relevant"
        elif expects_reply:
            reply_type = "context_relevant"
        else:
            reply_type = "short"
        return {
            "has_action": True,
            "reply_type": reply_type,
            "title": _mk_title(t),
            "summary": _mk_summary(t),
            "suggested_reply": "Got it — I’ll take care of it.",
            "confidence": 0.82,
        }

    if is_question:
        reply_type = "time_relevant" if has_time_signal else "context_relevant"
        return {
            "has_action": False,
            "reply_type": reply_type,
            "title": "Question",
            "summary": _mk_summary(t),
            "suggested_reply": "Got it — I’ll get back to you shortly.",
            "confidence": 0.76,
        }

    if is_suggestion:
        return {
            "has_action": False,
            "reply_type": "context_relevant",
            "title": "Update",
            "summary": _mk_summary(t),
            "suggested_reply": "Got it — thanks for the update.",
            "confidence": 0.74,
        }

    if is_status_update or expects_reply:
        # Status updates like "still waiting/pending" often don't require a reply.
        if re.search(
            r"\b(still pending|still waiting|waiting for|waiting on)\b",
            t,
            flags=re.IGNORECASE,
        ) and not expects_reply and not re.search(
            r"(\bupdate\s*[:\-]|\bquick update\b|\bblocker\b)",
            t,
            flags=re.IGNORECASE,
        ):
            return {
                "has_action": False,
                "reply_type": "none",
                "title": None,
                "summary": _mk_summary(t),
                "suggested_reply": None,
                "confidence": 0.74,
            }

        reply_type = (
            "time_relevant"
            if has_time_signal
            else "context_relevant"
        )
        return {
            "has_action": False,
            "reply_type": reply_type,
            "title": "Update",
            "summary": _mk_summary(t),
            "suggested_reply": "Thanks for the update — I’ll review it and get back to you.",
            "confidence": 0.74,
        }

    return None


# --------- Validation / Fallback ----------
def _fallback_info(text: str, reason: str) -> Dict[str, Any]:
    preview = (text or "").strip()
    preview = preview[:200] + ("..." if len(preview) > 200 else "")
    return {
        "has_action": False,
        "reply_type": "none",
        "title": None,
        "summary": preview if preview else "Empty message.",
        "suggested_reply": None,
        "confidence": 0.0,
        "needs_review": True,
        "error": reason,
    }


def _validate(result: Dict[str, Any], original_text: str) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return _fallback_info(original_text, "Classifier returned non-dict")

    has_action = bool(result.get("has_action", False))

    reply_type = str(result.get("reply_type", "none")).strip().lower()
    if reply_type not in ALLOWED_REPLY_TYPES:
        reply_type = "none"

    confidence = result.get("confidence", 0.5)
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    summary = (result.get("summary") or "").strip()
    if not summary:
        summary = (original_text or "").strip()
    summary = summary[:400]

    title = result.get("title", None)
    if title is not None:
        title = str(title).strip()[:120]
        if title == "":
            title = None

    suggested_reply = result.get("suggested_reply", None)
    if suggested_reply is not None:
        suggested_reply = str(suggested_reply).strip()[:800]
        if suggested_reply == "":
            suggested_reply = None

    if reply_type == "none":
        suggested_reply = None
    elif suggested_reply is None:
        if reply_type == "short":
            suggested_reply = "Got it, thank you."
        elif reply_type == "time_relevant":
            suggested_reply = "Got it — I’ll handle this as soon as possible."
        else:
            suggested_reply = "Thanks for the message — I’ll review it and get back to you."

    clean: Dict[str, Any] = {
        "has_action": has_action,
        "reply_type": reply_type,
        "title": title,
        "summary": summary,
        "confidence": confidence,
        "suggested_reply": suggested_reply,
    }

    if isinstance(result.get("tags"), list):
        clean["tags"] = [str(x)[:40] for x in result["tags"][:8]]

    return clean


SYSTEM_PROMPT = """You are a routing classifier for an assistant workflow.

Analyze an incoming work message or email and return ONLY valid JSON.

Your job is to decide:
1. whether the message contains a concrete action/task request
2. what kind of reply is appropriate

Return ONLY this JSON schema:
{
  "has_action": boolean,
  "reply_type": "none" | "short" | "time_relevant" | "context_relevant",
  "title": string | null,
  "summary": string,
  "suggested_reply": string | null,
  "confidence": number
}

Definitions:
- has_action = true if the sender asks the recipient to do something concrete
- has_action = false for pure updates, status checks, greetings, newsletters, or informational content

Important:
The input may include project context such as client name, project name, summary, blockers, and next steps.
Use that context to understand the incoming message better.
But classify the actual incoming message carefully and do not assume a new task exists unless the incoming message itself supports it.
"""


def classify(text: str, raw_text: str | None = None) -> Dict[str, Any]:
    """
    text:
        Enriched classifier input for the LLM.
        May include client/project/context.

    raw_text:
        Raw/clean original message text for heuristics only.
    """
    enriched_text = (text or "").strip()
    raw_input = (raw_text or text or "").strip()

    if not raw_input:
        return {
            "has_action": False,
            "reply_type": "none",
            "title": None,
            "summary": "Empty message.",
            "suggested_reply": None,
            "confidence": 0.9,
            "classification_source": "heuristic_fallback",
        }

    heuristic_result = _heuristic_classify(raw_input)

    # No OpenAI available -> degrade gracefully to heuristics
    if client is None:
        if heuristic_result is not None:
            out = _validate(heuristic_result, raw_input)
            out["classification_source"] = "heuristic_fallback"
            return out
        out = _fallback_info(raw_input, "OPENAI_API_KEY missing")
        out["classification_source"] = "heuristic_fallback"
        return out

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": enriched_text},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        content = resp.choices[0].message.content
        if not content:
            if heuristic_result is not None:
                out = _validate(heuristic_result, raw_input)
                out["classification_source"] = "heuristic_fallback"
                return out
            out = _fallback_info(raw_input, "Empty model response")
            out["classification_source"] = "heuristic_fallback"
            return out

        parsed = json.loads(content)
        validated = _validate(parsed, raw_input)
        did_override = False

        # Conservative override:
        # if heuristics are *very* confident and the LLM missed it,
        # promote has_action=True.
        #
        # Also: prevent obvious false-positive tasks caused by context leakage.
        # If the LLM marks an action but raw text doesn't look like a request
        # and heuristics classify it as non-action, demote has_action=False.
        if heuristic_result is not None:
            heuristic_validated = _validate(heuristic_result, raw_input)

            strong_override = _strong_override_action_request(raw_input)

            # 1) has_action corrections (strictly gated)
            if (
                heuristic_validated.get("has_action")
                and not validated.get("has_action")
                and strong_override
            ):
                did_override = True
                validated["has_action"] = True

                if not validated.get("title"):
                    validated["title"] = heuristic_validated.get("title")

                if validated.get("reply_type") == "none":
                    validated["reply_type"] = heuristic_validated.get("reply_type", "short")

                if not validated.get("suggested_reply"):
                    validated["suggested_reply"] = heuristic_validated.get("suggested_reply")

                validated["confidence"] = max(
                    float(validated.get("confidence", 0.0)),
                    float(heuristic_validated.get("confidence", 0.0)),
                )

            elif (
                validated.get("has_action")
                and not heuristic_validated.get("has_action")
                and not strong_override
            ):
                did_override = True
                validated["has_action"] = False

                if not validated.get("title"):
                    validated["title"] = heuristic_validated.get("title")

                if not validated.get("suggested_reply"):
                    validated["suggested_reply"] = heuristic_validated.get("suggested_reply")

                validated["confidence"] = min(
                    float(validated.get("confidence", 0.0)),
                    float(heuristic_validated.get("confidence", 0.0)),
                )

            # 2) reply_type reconciliation (both action + non-action)
            hv_rt = str(heuristic_validated.get("reply_type") or "none").strip().lower()
            v_rt = str(validated.get("reply_type") or "none").strip().lower()

            if hv_rt in ALLOWED_REPLY_TYPES:
                # Suggestions/plans mentioning time should not become "time_relevant" urgency.
                if (
                    not validated.get("has_action")
                    and hv_rt == "context_relevant"
                    and v_rt == "time_relevant"
                    and _RE_SUGGESTION_NOT_REQUEST.search(_normalize_for_heuristics(raw_input))
                ):
                    did_override = True
                    validated["reply_type"] = "context_relevant"
                    validated["confidence"] = min(
                        float(validated.get("confidence", 0.0)),
                        float(heuristic_validated.get("confidence", 0.0)),
                    )

                # Prefer conservative "none" when heuristics are confident it's just an update.
                if (
                    not validated.get("has_action")
                    and hv_rt == "none"
                    and v_rt != "none"
                ):
                    did_override = True
                    validated["reply_type"] = "none"
                    validated["suggested_reply"] = None

                # If heuristics detect context/time relevance, don't let the model under-classify.
                elif hv_rt in {"context_relevant", "time_relevant"}:
                    should_upgrade = (
                        v_rt in {"none", "short"}
                        or (hv_rt == "time_relevant" and v_rt == "context_relevant")
                    )
                    if should_upgrade:
                        did_override = True
                        validated["reply_type"] = hv_rt

                        if not validated.get("title"):
                            validated["title"] = heuristic_validated.get("title")

                        if not validated.get("suggested_reply"):
                            validated["suggested_reply"] = heuristic_validated.get("suggested_reply")

                        validated["confidence"] = min(
                            float(validated.get("confidence", 0.0)),
                            float(heuristic_validated.get("confidence", 0.0)),
                        )

        validated["classification_source"] = (
            "llm_with_heuristic_override" if did_override else "llm"
        )
        return validated

    except json.JSONDecodeError:
        if heuristic_result is not None:
            out = _validate(heuristic_result, raw_input)
            out["classification_source"] = "heuristic_fallback"
            return out
        out = _fallback_info(raw_input, "Model returned non-JSON")
        out["classification_source"] = "heuristic_fallback"
        return out
    except Exception as e:
        if heuristic_result is not None:
            out = _validate(heuristic_result, raw_input)
            out["classification_source"] = "heuristic_fallback"
            return out
        out = _fallback_info(raw_input, f"Classifier error: {e}")
        out["classification_source"] = "heuristic_fallback"
        return out