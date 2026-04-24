"""
Regression tests that Gmail / Slack messages mentioning a project name
route to that project (creating or reusing it) instead of collapsing
every inbound message into the ``General`` bucket.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _bootstrap_backend_path() -> None:
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    p = str(backend)
    if p not in sys.path:
        sys.path.insert(0, p)


_bootstrap_backend_path()

import services.unified_processor as up  # noqa: E402


class _Capturing:
    """Captures keyword arguments passed into the resolver so the test can
    assert on what the processor actually fed in.
    """

    def __init__(self) -> None:
        self.captured: dict[str, Any] = {}

    def __call__(self, **kwargs: Any) -> tuple[int, str, str, float, bool]:
        self.captured = kwargs
        project_name = kwargs.get("explicit_project_name") or kwargs.get(
            "fallback_project_name"
        ) or "General"
        return 999, project_name, "explicit_project_name", 1.0, False


def _make_normalized(*, source: str, raw_text: str, text_for_classification: str) -> dict[str, Any]:
    return {
        "source": source,
        "workspace_id": "ws-test",
        "source_id": f"{source}:src-test",
        "channel": "test-channel",
        "thread_id": "thread-test",
        "ts": "2026-04-24T22:00:00Z",
        "sender": "sender@example.com",
        "user_id": "sender@example.com",
        "recipient": None,
        "subject": "Request to perform tests for Vana project",
        "raw_text": raw_text,
        "text_for_classification": text_for_classification,
        "payload": {"skip_draft": True, "skip_task_link": True},
        "client_name_hint": "Inbox",
        "project_name_hint": None,
        "channel_type": None,
    }


def _install_stubs(monkeypatch) -> _Capturing:
    capturing = _Capturing()
    monkeypatch.setattr(up, "resolve_project_for_client", capturing)
    monkeypatch.setattr(up, "ensure_client", lambda name: 42)
    monkeypatch.setattr(
        up,
        "insert_message_if_new",
        lambda **_: (True, 1001),
    )
    monkeypatch.setattr(up, "get_message_context_for_source_id", lambda **_: None)
    monkeypatch.setattr(up, "get_project_context", lambda _pid: None)
    monkeypatch.setattr(up, "attach_message_context", lambda **_: None)
    monkeypatch.setattr(up, "log_event", lambda **_: None)
    monkeypatch.setattr(up, "insert_metrics_event", lambda _ev: 1)
    monkeypatch.setattr(
        up,
        "build_metrics_event",
        lambda **_: {"source": "gmail", "status": "ok"},
    )
    monkeypatch.setattr(up, "build_continuity_context", lambda **_: {"summary": {}})
    monkeypatch.setattr(
        up,
        "score_message_importance",
        lambda **_: {"importance_score": 0, "importance_level": "low", "importance_reasons": []},
    )
    monkeypatch.setattr(
        up,
        "analyze_scheduling_signals",
        lambda **_: {
            "has_schedule_signal": False,
            "due_hint_text": None,
            "normalized_due": None,
            "time_pressure_level": None,
            "overdue_risk": None,
            "upcoming_risk": None,
            "task_due_datetime": None,
        },
    )
    monkeypatch.setattr(
        up,
        "extract_project_updates",
        lambda _text: {"has_project_update": False, "fields": {}, "confidence": 0.0},
    )
    monkeypatch.setattr(
        up,
        "detect_follow_up_candidate",
        lambda _text: {"is_candidate": False, "confidence": 0.0, "reason": "none"},
    )
    monkeypatch.setattr(
        up,
        "update_project_context_from_candidate",
        lambda *_args, **_kw: {
            "updated": False,
            "changed_fields": [],
            "skipped_reason": "stub",
            "before": None,
            "after": None,
        },
    )
    monkeypatch.setattr(
        up,
        "create_follow_up_from_candidate",
        lambda **_: {"created": False, "follow_up_id": None, "reason": "stub"},
    )
    monkeypatch.setattr(
        up,
        "run_task_link_phase",
        lambda **_: (
            {"matched": False, "reason": "stub", "task_id": None, "grafik_task_id": None, "confidence": 0.0, "needs_review": False},
            True,
            "stub",
        ),
    )
    monkeypatch.setattr(
        up,
        "classify_and_enrich",
        lambda **_: (
            {"has_action": False, "reply_type": "none"},
            "",
            "none",
            False,
        ),
    )
    monkeypatch.setattr(
        up,
        "should_suppress_as_non_actionable",
        lambda **_: (False, None),
    )
    monkeypatch.setattr(
        up,
        "compute_reply_policy",
        lambda **_: {
            "should_reply": False,
            "reply_mode": "none",
            "reason": "stub",
            "confidence": 0.0,
            "needs_review": False,
        },
    )
    monkeypatch.setattr(up, "maybe_generate_reply_text", lambda **_: None)
    monkeypatch.setattr(up, "should_create_gmail_draft", lambda **_: False)
    return capturing


def test_gmail_message_mentioning_project_creates_explicit_hint(monkeypatch) -> None:
    """
    A Gmail message whose subject / body mentions "Vana project" should
    be routed to the resolver with ``explicit_project_name='vana project'``
    so the resolver either reuses an existing Vana row or creates one.
    """
    capturing = _install_stubs(monkeypatch)

    text = (
        "Subject: Request to perform tests for Vana project "
        "Body: Please run the full suite before Friday."
    )
    normalized = _make_normalized(
        source="gmail",
        raw_text=text,
        text_for_classification=text,
    )

    up.process_normalized_message(normalized)

    assert capturing.captured, "resolver was never called"
    assert capturing.captured["explicit_project_name"] == "vana project"
    assert capturing.captured["fallback_project_name"] == "General"


def test_slack_message_mentioning_project_creates_explicit_hint(monkeypatch) -> None:
    capturing = _install_stubs(monkeypatch)

    text = "status update on the Acme project: we're on track for Friday"
    normalized = _make_normalized(
        source="slack",
        raw_text=text,
        text_for_classification=text,
    )

    up.process_normalized_message(normalized)

    assert capturing.captured["explicit_project_name"] == "acme project"


def test_generic_message_without_project_mention_has_no_hint(monkeypatch) -> None:
    """
    When the message does not mention a project, we must not invent one.
    The resolver should fall through to its name-matching / fallback
    logic with no explicit hint.
    """
    capturing = _install_stubs(monkeypatch)

    text = "schedule a meeting on saturday at 15"
    normalized = _make_normalized(
        source="slack",
        raw_text=text,
        text_for_classification=text,
    )

    up.process_normalized_message(normalized)

    assert capturing.captured["explicit_project_name"] is None
    assert capturing.captured["fallback_project_name"] == "General"
