from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_backend_path() -> None:
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    p = str(backend)
    if p not in sys.path:
        sys.path.insert(0, p)


def test_bare_24h_hour_is_accepted() -> None:
    _bootstrap_backend_path()
    from application.services.calendar_meeting_action import _clock_from_text

    text = (
        "schedule a meeting for tomorrow at 18 for 30 mins; "
        "with vanesa.taneva12@gmail.com, on teams, about lucient project"
    )
    assert _clock_from_text(text) == (18, 0)
