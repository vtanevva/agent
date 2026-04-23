"""Natural-language chat → SQLite task shortcut (title + deadline parsing)."""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_backend_path() -> None:
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    p = str(backend)
    if p not in sys.path:
        sys.path.insert(0, p)


def test_extract_task_title_add_task_to_by() -> None:
    _bootstrap_backend_path()
    from application.services.chat_task_action import _extract_task_title

    t = _extract_task_title("add a task to finish lucient project by sunday at 18")
    assert t == "finish lucient project"


def test_looks_like_task_request() -> None:
    _bootstrap_backend_path()
    from application.services.chat_task_action import _looks_like_task_creation_request

    assert _looks_like_task_creation_request("add a task to finish X by Sunday")
    assert not _looks_like_task_creation_request("schedule a meeting on Monday at 3")
