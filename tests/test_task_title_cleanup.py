"""
Task titles must not leak the classifier-input labels ``Subject:`` / ``Body:``
or a ``<Source>:`` prefix into the Home UI.

This was the bug the user hit in screenshot ``Gmail: Subject: Body: Do the
dishes please`` — ``build_task_title_and_description`` used to fall back to
``text_for_classification`` (which is wrapped for the classifier as
``"Subject: <s>\nBody: <b>"``) and prefix it with ``"Gmail: "``. The result
rendered on Home as a task titled ``"Gmail: Subject: Body: Do the dishes please"``.

We test two layers so both new rows and pre-existing DB rows come out clean:
  1. ``build_task_title_and_description`` generates a plain body-derived title
     when the classifier has no title and the email has no subject.
  2. ``_clean_task_title`` strips stale ``<Source>:`` / ``Subject:`` / ``Body:``
     prefixes so rows written before the fix also render nicely.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_backend_path() -> None:
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    p = str(backend)
    if p not in sys.path:
        sys.path.insert(0, p)


def _default_build_kwargs(**overrides):
    base = dict(
        source="gmail",
        classification={},
        subject="",
        text_for_classification="Subject: Body: Do the dishes please",
        raw_text="Do the dishes please",
        client_name=None,
        project_name=None,
        project_resolution_reason=None,
        project_confidence=None,
        needs_project_review=False,
        workspace_id=None,
        channel=None,
        channel_type=None,
        thread_id=None,
        ts=None,
        sender=None,
        recipient=None,
        user_id=None,
        project_update_candidate={},
        follow_up_candidate={},
        project_context=None,
        classification_input=None,
    )
    base.update(overrides)
    return base


def test_build_task_title_prefers_classifier_title() -> None:
    _bootstrap_backend_path()
    from services.task_service import build_task_title_and_description

    title, _desc = build_task_title_and_description(
        **_default_build_kwargs(classification={"title": "Buy groceries"})
    )
    assert title == "Buy groceries"


def test_build_task_title_uses_subject_when_no_classifier_title() -> None:
    _bootstrap_backend_path()
    from services.task_service import build_task_title_and_description

    title, _desc = build_task_title_and_description(
        **_default_build_kwargs(subject="Lunch tomorrow?")
    )
    assert title == "Lunch tomorrow?"
    assert "Gmail:" not in title
    assert "Subject:" not in title
    assert "Body:" not in title


def test_build_task_title_falls_back_to_body_not_wrapped_classifier_input() -> None:
    _bootstrap_backend_path()
    from services.task_service import build_task_title_and_description

    title, _desc = build_task_title_and_description(**_default_build_kwargs())
    assert title == "Do the dishes please"
    assert "Gmail:" not in title
    assert "Subject:" not in title
    assert "Body:" not in title


def test_build_task_title_handles_completely_empty_inputs() -> None:
    _bootstrap_backend_path()
    from services.task_service import build_task_title_and_description

    title, _desc = build_task_title_and_description(
        **_default_build_kwargs(
            subject="",
            text_for_classification="",
            raw_text="",
        )
    )
    # Empty inputs still produce *something* so the UI never renders "".
    assert title
    assert "Subject: Body:" not in title


def test_clean_task_title_strips_legacy_labels() -> None:
    _bootstrap_backend_path()
    from api.routes.action_items import _clean_task_title

    assert (
        _clean_task_title("Gmail: Subject: Body: Do the dishes please")
        == "Do the dishes please"
    )
    assert _clean_task_title("Slack: Body: ping @here") == "ping @here"
    assert _clean_task_title("Chat: Review RFP by Friday") == "Review RFP by Friday"
    # Clean titles stay clean.
    assert _clean_task_title("Buy groceries") == "Buy groceries"
    # Titles with colons that aren't the stale prefix stay intact.
    assert (
        _clean_task_title("Q2 review: prep slides")
        == "Q2 review: prep slides"
    )


def test_clean_task_title_safe_on_empty_and_none() -> None:
    _bootstrap_backend_path()
    from api.routes.action_items import _clean_task_title

    assert _clean_task_title(None) == ""
    assert _clean_task_title("") == ""
    assert _clean_task_title("   ") == ""
