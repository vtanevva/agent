"""
Best-effort extraction of an explicit "<name> project" phrase from a
user-typed chat line.

The unified processor (``project_resolution.resolve_project_for_client``)
treats this hint as the **highest-confidence** signal, so it must only
fire when the user really named a project. If no safe hint can be
produced we return ``None`` and let the resolver fall back to matching
existing project names in the raw text or the "General" bucket.

History:
    An older implementation also invented project names from
    ``about/for/on/re/regarding X`` phrases by appending " project"
    to anything it captured. That produced bogus projects such as
    "saturday at 15 project" whenever a user typed
    "schedule a meeting on saturday at 15". We explicitly avoid that
    here: we only return a hint when the word "project" is present in
    the user's text.
"""

from __future__ import annotations

import re


_MAX_NAME_WORDS = 3
_MAX_HINT_LENGTH = 120

# Words that cannot stand in for a project name on their own.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "about",
        "for",
        "on",
        "at",
        "in",
        "to",
        "of",
        "re",
        "regarding",
        "my",
        "our",
        "your",
        "their",
        "his",
        "her",
        "its",
        "some",
        "any",
        "new",
        "old",
        "next",
        "last",
        "previous",
        "current",
        "upcoming",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "today",
        "tomorrow",
        "yesterday",
        "tonight",
        "morning",
        "afternoon",
        "evening",
        "night",
        "week",
        "weekend",
        "weekday",
        "month",
        "year",
        "hour",
        "minute",
        "day",
        "am",
        "pm",
        "meeting",
        "call",
        "chat",
        "sync",
        "standup",
        "lunch",
        "dinner",
        "breakfast",
        "appointment",
        # Email header tokens that appear in Gmail-style text assembled
        # by ``prepare_email_for_classification`` ("Subject: ... Body: ...").
        "subject",
        "body",
        "from",
        "sent",
        "cc",
        "bcc",
        "fwd",
        "fw",
    }
)

# Tokens whose appearance signals the left-edge of a project name.
# Either a determiner ("the marketing project") or a preposition
# ("tests for vana project"). Everything AFTER the last such token
# and BEFORE "project" is the candidate name.
_NAME_BOUNDARIES: frozenset[str] = frozenset(
    {
        # determiners
        "the",
        "my",
        "our",
        "your",
        "their",
        "his",
        "her",
        "its",
        "a",
        "an",
        # prepositions / connectors commonly used before a project name
        "about",
        "for",
        "on",
        "in",
        "to",
        "of",
        "re",
        "regarding",
        "at",
        # email header labels so "Subject: X project" still resolves to
        # the name "X" without leaking "subject" into the hint
        "subject",
        "body",
        "from",
        "sent",
        "cc",
        "bcc",
        "fwd",
        "fw",
    }
)

_PROJECT_WORD_RE = re.compile(r"(?i)\bproject\b")
_WORD_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def _is_meaningful_word(word: str) -> bool:
    """Non-stopword, non-digit, contains at least one letter."""
    if not word:
        return False
    lowered = word.lower()
    if lowered in _STOPWORDS:
        return False
    if lowered.isdigit():
        return False
    if not any(ch.isalpha() for ch in lowered):
        return False
    return True


def safe_project_hint(text: str) -> str | None:
    """
    Return a normalized ``"<name> project"`` hint if the user clearly
    referred to a project by name. Otherwise return ``None``.
    """
    msg = " ".join((text or "").strip().split())
    if not msg:
        return None

    for match in _PROJECT_WORD_RE.finditer(msg):
        prefix = msg[: match.start()].rstrip()
        tokens = [t.lower() for t in _WORD_TOKEN_RE.findall(prefix)]
        if not tokens:
            continue

        # Prefer the rightmost determiner / preposition within the last
        # few tokens as the left edge of the project name. This lets us
        # pull the real name out of phrases such as:
        #   "I'll finish the marketing project"  -> "marketing"
        #   "Request to perform tests for Vana project" -> "vana"
        # instead of including the surrounding verbs / subjects.
        tail_window = tokens[-(_MAX_NAME_WORDS + 1) :]
        cut_idx: int | None = None
        for i in range(len(tail_window) - 1, -1, -1):
            if tail_window[i] in _NAME_BOUNDARIES:
                cut_idx = i
                break

        if cut_idx is not None:
            tail = tail_window[cut_idx + 1 :]
        else:
            tail = tokens[-_MAX_NAME_WORDS:]

        while tail and tail[0] in _STOPWORDS:
            tail.pop(0)
        if not tail:
            continue
        # Require at least one real word; a tail that's only numbers or
        # stopwords means the user was talking about a time or date,
        # not a project.
        if not any(_is_meaningful_word(t) for t in tail):
            continue

        tail = tail[-_MAX_NAME_WORDS:]
        name = " ".join(tail) + " project"
        if len(name) > _MAX_HINT_LENGTH:
            name = name[:_MAX_HINT_LENGTH].rstrip()
        return name

    return None


__all__ = ["safe_project_hint"]
