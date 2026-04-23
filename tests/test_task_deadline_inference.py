"""
Deadline / timing inference from inbound message text (scheduling_awareness).

Used by unified_processor to set ``classification["due_datetime"]`` so SQLite tasks
and the Expo week/month scheduler can place items on the right day.

Run from repo root::

    python tests/test_task_deadline_inference.py

Or::

    pytest tests/test_task_deadline_inference.py -q
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


def test_finish_by_tomorrow_maps_to_next_day_noon_utc() -> None:
    _bootstrap_backend_path()
    from services.scheduling_awareness import analyze_scheduling_signals

    r = analyze_scheduling_signals(
        clean_text="Please finish this by tomorrow — thanks!",
        classification=None,
        now_utc="2026-04-23T14:30:00Z",
    )
    assert r.get("due_hint_text") == "by tomorrow"
    assert r.get("normalized_due", {}).get("type") == "date"
    assert r.get("normalized_due", {}).get("value") == "2026-04-24"
    assert r.get("task_due_datetime") == "2026-04-24T12:00:00Z"


def test_by_today_with_clock_time_is_datetime() -> None:
    _bootstrap_backend_path()
    from services.scheduling_awareness import analyze_scheduling_signals

    r = analyze_scheduling_signals(
        clean_text="Can you send the signed PDF by 3pm today?",
        classification=None,
        now_utc="2026-04-23T10:00:00Z",
    )
    assert r.get("task_due_datetime") == "2026-04-23T15:00:00Z"


def test_vague_message_has_no_task_due_datetime() -> None:
    _bootstrap_backend_path()
    from services.scheduling_awareness import analyze_scheduling_signals

    r = analyze_scheduling_signals(
        clean_text="Thanks for the update, looks good overall.",
        classification=None,
        now_utc="2026-04-23T12:00:00Z",
    )
    assert r.get("task_due_datetime") is None


def test_due_by_prefix_stripped_for_weekday() -> None:
    _bootstrap_backend_path()
    from services.scheduling_awareness import analyze_scheduling_signals

    r = analyze_scheduling_signals(
        clean_text="We need the report due by Friday",
        classification=None,
        now_utc="2026-04-20T12:00:00Z",  # Monday
    )
    assert r.get("normalized_due", {}).get("type") == "date"
    assert r.get("normalized_due", {}).get("value") == "2026-04-24"
    assert r.get("task_due_datetime") == "2026-04-24T12:00:00Z"


def main() -> None:
    test_finish_by_tomorrow_maps_to_next_day_noon_utc()
    test_by_today_with_clock_time_is_datetime()
    test_vague_message_has_no_task_due_datetime()
    test_due_by_prefix_stripped_for_weekday()
    print("test_task_deadline_inference: all passed")


if __name__ == "__main__":
    main()
