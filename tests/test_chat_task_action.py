"""
Unit tests for chat-side task shortcut parsing (``chat_task_action``).

Run from repo root::

    python tests/test_chat_task_action.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


def _bootstrap_backend_path() -> None:
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    p = str(backend)
    if p not in sys.path:
        sys.path.insert(0, p)
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def test_meta_title_create_a_task_to_create_a_task() -> None:
    _bootstrap_backend_path()
    from application.services.chat_task_action import _extract_task_title, _looks_like_task_creation_request

    msg = "create a task to create a task documenting the API by Friday"
    assert _looks_like_task_creation_request(msg)
    assert _extract_task_title(msg) == "create a task documenting the API"


def test_verbs_make_set_open_todo() -> None:
    _bootstrap_backend_path()
    from application.services.chat_task_action import _extract_task_title, _looks_like_task_creation_request

    for msg in (
        "make a new task to buy milk by tomorrow",
        "set a task for calling dad before Sunday",
        "set up a task to deploy the fix by Monday",
        "open a todo to review the PR by 5pm Friday",
        "log an action item to update the spec before next Tuesday",
    ):
        assert _looks_like_task_creation_request(msg), msg
        t = _extract_task_title(msg)
        assert t and len(t) > 3, msg


def test_deadline_boundary_before_until_due_by() -> None:
    _bootstrap_backend_path()
    from application.services.chat_task_action import _extract_task_title, _looks_like_task_creation_request

    msg = "add a task to finish the deck before Monday"
    assert _looks_like_task_creation_request(msg)
    assert _extract_task_title(msg) == "finish the deck"

    msg2 = "create task to ship v2 until Friday"
    assert _looks_like_task_creation_request(msg2)
    assert _extract_task_title(msg2) == "ship v2"

    msg3 = "make a task to file taxes due by April 15"
    assert _looks_like_task_creation_request(msg3)
    assert _extract_task_title(msg3) == "file taxes"


def test_colon_form() -> None:
    _bootstrap_backend_path()
    from application.services.chat_task_action import _extract_task_title, _looks_like_task_creation_request

    msg = "create a task: review Q3 numbers by Wednesday"
    assert _looks_like_task_creation_request(msg)
    assert _extract_task_title(msg) == "review Q3 numbers"


def test_task_to_schedule_meeting_still_task_not_calendar_guard() -> None:
    _bootstrap_backend_path()
    from application.services.chat_task_action import _looks_like_task_creation_request

    msg = "create a task to schedule a meeting with Acme by Thursday"
    assert _looks_like_task_creation_request(msg)


def test_no_deadline_still_creates_task() -> None:
    _bootstrap_backend_path()
    from application.services.chat_task_action import _extract_task_title, _looks_like_task_creation_request

    msg = "add a task to do the dishes"
    assert _looks_like_task_creation_request(msg)
    assert _extract_task_title(msg) == "do the dishes"


def test_try_create_calls_unified_path() -> None:
    _bootstrap_backend_path()
    with patch("application.orchestrators.event_orchestrator.handle_normalized_event") as h:
        from application.services.chat_task_action import try_create_task_from_chat

        reply = try_create_task_from_chat(
            "please add a new task to email legal before Friday",
            {"timezone": "UTC"},
            session_id="sess-test",
        )
        assert reply and "email legal" in reply
        assert h.called
        args = h.call_args[0][0]
        assert args.get("source") == "chat_task"
        assert args["payload"]["classification_override"]["title"] == "email legal"
        assert "due_datetime" in args["payload"]["classification_override"]


def test_try_create_without_due_omits_datetime() -> None:
    _bootstrap_backend_path()
    with patch("application.orchestrators.event_orchestrator.handle_normalized_event") as h:
        from application.services.chat_task_action import try_create_task_from_chat

        reply = try_create_task_from_chat(
            "add a task to do the dishes",
            {"timezone": "UTC"},
            session_id="sess-nd",
        )
        assert reply and "no due date" in reply.lower()
        assert h.called
        o = h.call_args[0][0]["payload"]["classification_override"]
        assert o.get("title") == "do the dishes"
        assert "due_datetime" not in o


def main() -> None:
    test_meta_title_create_a_task_to_create_a_task()
    test_verbs_make_set_open_todo()
    test_deadline_boundary_before_until_due_by()
    test_colon_form()
    test_task_to_schedule_meeting_still_task_not_calendar_guard()
    test_try_create_calls_unified_path()
    test_no_deadline_still_creates_task()
    test_try_create_without_due_omits_datetime()
    print("test_chat_task_action: all passed")


if __name__ == "__main__":
    main()
