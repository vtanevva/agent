from __future__ import annotations

import json
import re
from typing import Any

from storage.sqlite_db import get_recent_tasks_for_client, get_recent_tasks_for_project


CONFIDENCE_THRESHOLD = 0.75

_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "for",
    "on",
    "in",
    "at",
    "by",
    "with",
    "this",
    "that",
    "it",
    "we",
    "you",
    "i",
    "our",
    "my",
    "your",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "as",
    "yet",
    "just",
    "still",
}

_RE_TOKEN = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)

_CONTINUATION_PHRASES = [
    "any update",
    "follow up",
    "did we hear back",
    "did you hear back",
    "did we send",
    "did you send",
    "sent yet",
    "send that",
    "that timeline",
    "update on that",
    "update on this",
]


def _tokens(text: str) -> set[str]:
    t = (text or "").lower()
    toks = {m.group(0) for m in _RE_TOKEN.finditer(t)}
    return {x for x in toks if x not in _STOPWORDS}


def _safe_json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    if isinstance(value, str):
        s = value.strip()
        # tasks.classification_json is a JSON string; keep as text for token overlap
        return s
    return str(value)


def _contains_continuation_phrase(text: str) -> bool:
    lower = (text or "").lower()
    return any(p in lower for p in _CONTINUATION_PHRASES)


def _task_text(task: dict[str, Any]) -> str:
    return " ".join(
        [
            str(task.get("title") or ""),
            str(task.get("description") or ""),
            _safe_json_text(task.get("classification_json")),
        ]
    ).strip()


def _score_overlap(message_tokens: set[str], task_tokens: set[str]) -> float:
    if not message_tokens or not task_tokens:
        return 0.0
    inter = message_tokens & task_tokens
    union = message_tokens | task_tokens
    jaccard = len(inter) / max(1, len(union))
    recall = len(inter) / max(1, len(message_tokens))
    return max(jaccard, recall)


def find_existing_task_for_message(
    *,
    client_id: int | None,
    project_id: int | None,
    raw_text: str,
    classification: dict,
    follow_up_candidate: dict | None = None,
) -> dict[str, Any]:
    has_action = bool((classification or {}).get("has_action"))
    if not has_action:
        return {
            "matched": False,
            "reason": "not_action",
            "task_id": None,
            "grafik_task_id": None,
            "confidence": 0.0,
            "needs_review": False,
        }

    if not (project_id or client_id):
        return {
            "matched": False,
            "reason": "missing_scope",
            "task_id": None,
            "grafik_task_id": None,
            "confidence": 0.0,
            "needs_review": True,
        }

    msg = (raw_text or "").strip()
    msg_tokens = _tokens(msg)
    continuation = _contains_continuation_phrase(msg)
    is_follow_up = bool((follow_up_candidate or {}).get("is_follow_up"))

    # 1) Prefer project-scoped tasks
    tasks: list[dict[str, Any]] = []
    scope_reason = None
    if project_id:
        tasks = get_recent_tasks_for_project(project_id, limit=10)
        scope_reason = "project_recent"
    if (not tasks) and client_id:
        tasks = get_recent_tasks_for_client(client_id, limit=10)
        scope_reason = "client_recent"

    if not tasks:
        return {
            "matched": False,
            "reason": "no_recent_tasks",
            "task_id": None,
            "grafik_task_id": None,
            "confidence": 0.0,
            "needs_review": False,
        }

    # If it's strongly a follow-up continuation and there is exactly one recent task,
    # link conservatively to that task.
    if (continuation or is_follow_up) and len(tasks) == 1:
        t0 = tasks[0]
        linked_task_id = t0.get("grafik_task_id")
        return {
            "matched": True,
            "reason": f"{scope_reason}:single_task_follow_up",
            "task_id": t0.get("id"),
            "grafik_task_id": linked_task_id,
            "confidence": 0.85,
            "needs_review": False,
        }

    best = None
    best_score = 0.0
    second_score = 0.0

    for t in tasks:
        task_tokens = _tokens(_task_text(t))
        s = _score_overlap(msg_tokens, task_tokens)
        if s > best_score:
            second_score = best_score
            best_score = s
            best = t
        elif s > second_score:
            second_score = s

    # Boost when message looks like a continuation/follow-up.
    boost = 0.0
    if continuation:
        boost += 0.15
    if is_follow_up:
        boost += 0.15

    confidence = min(1.0, best_score + boost)

    clear_winner = best_score >= 0.20 and (best_score - second_score) >= 0.10

    # Conservative policy:
    # - If this message looks like a continuation (follow-up phrases or follow_up detector),
    #   allow matching at the normal threshold.
    # - If it does NOT look like a continuation, only match when extremely confident,
    #   otherwise prefer creating a new task.
    if continuation or is_follow_up:
        ok_to_match = confidence >= CONFIDENCE_THRESHOLD and (best_score >= 0.25 or clear_winner)
    else:
        ok_to_match = confidence >= 0.90 and best_score >= 0.50 and clear_winner

    if ok_to_match and best is not None:
        linked_task_id = best.get("grafik_task_id")
        return {
            "matched": True,
            "reason": f"{scope_reason}:overlap",
            "task_id": best.get("id"),
            "grafik_task_id": linked_task_id,
            "confidence": confidence,
            "needs_review": False,
        }

    needs_review = (continuation or is_follow_up) and confidence >= 0.60
    linked_task_id = best.get("grafik_task_id") if best else None
    return {
        "matched": False,
        "reason": f"{scope_reason}:no_confident_match",
        "task_id": best.get("id") if best else None,
        "grafik_task_id": linked_task_id,
        "confidence": confidence,
        "needs_review": needs_review,
    }

