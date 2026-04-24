"""
Regression tests for ``chat_project_hint.safe_project_hint``.

Historically the chat orchestrator would invent project names out of
prepositional phrases such as "on saturday at 15", producing bogus
projects like ``"saturday at 15 project"``. We only want to produce a
hint when the user explicitly refers to a project by name.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _bootstrap_backend_path() -> None:
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    p = str(backend)
    if p not in sys.path:
        sys.path.insert(0, p)


_bootstrap_backend_path()

from services.chat_project_hint import safe_project_hint  # noqa: E402


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "hi",
        "schedule a meeting on saturday at 15",
        "can we meet on saturday at 4",
        "let's sync on monday at 9am",
        "ping me tomorrow",
        "remind me to call the vet",
        "add a task to send the deck",
        "what's on my plate this week",
        "on the",
        "for now",
        "about this",
    ],
)
def test_no_hint_when_project_word_absent(text: str) -> None:
    """We must never fabricate a project name from generic phrasing.

    In particular "saturday at 15", "saturday at 4" and similar
    time/date phrases must NOT become phantom projects.
    """
    assert safe_project_hint(text) is None


@pytest.mark.parametrize(
    "text",
    [
        # Pure date/time phrases with the word "project" appended but no
        # real noun — must not leak through.
        "saturday at 15 project",
        "at 4 project",
        "tomorrow project",
        "on monday project",
        "this week project",
        "the project",
        "a project",
    ],
)
def test_rejects_stopword_only_names(text: str) -> None:
    assert safe_project_hint(text) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("I'll finish the marketing project tomorrow", "marketing project"),
        ("about the lucient project", "lucient project"),
        ("working on the q4 roadmap project next week", "q4 roadmap project"),
        ("status update for the onboarding project", "onboarding project"),
        ("Please review the design system project draft", "design system project"),
        ("The Marketing Project needs a kickoff", "marketing project"),
    ],
)
def test_extracts_clean_name_when_project_mentioned(text: str, expected: str) -> None:
    assert safe_project_hint(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        # Gmail-style text shaped by prepare_email_for_classification
        # (subject + body merged into a single string).
        (
            "Subject: Request to perform tests for Vana project "
            "Body: Please run the full suite before Friday.",
            "vana project",
        ),
        (
            "Subject: Vana project - app webscreen completion "
            "Body: We're blocked on the hero copy, can you review?",
            "vana project",
        ),
        (
            "Subject: Kickoff for the Acme project "
            "Body: Agenda attached, please confirm.",
            "acme project",
        ),
        (
            "Subject: Weekly status "
            "Body: The onboarding project is on track, no blockers.",
            "onboarding project",
        ),
    ],
)
def test_extracts_from_gmail_style_text(text: str, expected: str) -> None:
    assert safe_project_hint(text) == expected


def test_caps_name_length() -> None:
    long_name = "x" * 200
    text = f"about the {long_name} project"
    hint = safe_project_hint(text)
    assert hint is not None
    assert len(hint) <= 120
