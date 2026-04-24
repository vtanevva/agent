"""
Regression tests for project name normalization inside
``resolve_project_for_client``.

The user wants every project name stored in Title Case regardless of
how the hint arrived ("perry project", "PERRY PROJECT", "Perry project"
must all resolve to "Perry Project"). Reuse must remain case-insensitive
so we never create duplicates.
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

import services.project_resolution as pr  # noqa: E402
from services.project_resolution import _canonicalize_project_name  # noqa: E402


class _FakeDB:
    """In-memory stub mirroring the SQLite helpers used by the resolver."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._next_id = 1

    def list_projects_for_client(self, client_id: int) -> list[dict[str, Any]]:
        return [dict(r) for r in self.rows if r["client_id"] == client_id]

    def get_project_by_name(self, client_id: int, name: str) -> dict[str, Any] | None:
        target = (name or "").strip().lower()
        for r in self.rows:
            if r["client_id"] == client_id and r["name"].strip().lower() == target:
                return dict(r)
        return None

    def create_project(
        self,
        client_id: int,
        name: str,
        description: str | None = None,
        status: str | None = "active",
        priority: str | None = None,
        deadline: str | None = None,
    ) -> int:
        row = {
            "id": self._next_id,
            "client_id": client_id,
            "name": name.strip(),
            "description": description,
            "status": status,
            "priority": priority,
            "deadline": deadline,
        }
        self._next_id += 1
        self.rows.append(row)
        return int(row["id"])


def _install_fake_db(monkeypatch) -> _FakeDB:
    fake = _FakeDB()
    monkeypatch.setattr(pr, "list_projects_for_client", fake.list_projects_for_client)
    monkeypatch.setattr(pr, "get_project_by_name", fake.get_project_by_name)
    monkeypatch.setattr(pr, "create_project", fake.create_project)
    return fake


def test_canonicalize_simple() -> None:
    assert _canonicalize_project_name("perry project") == "Perry Project"
    assert _canonicalize_project_name("PERRY PROJECT") == "Perry Project"
    assert _canonicalize_project_name("  Perry   project  ") == "Perry Project"


def test_canonicalize_preserves_digit_prefix() -> None:
    assert _canonicalize_project_name("q4 roadmap project") == "Q4 Roadmap Project"
    assert _canonicalize_project_name("3d modeling project") == "3D Modeling Project"


def test_canonicalize_empty() -> None:
    assert _canonicalize_project_name("") == ""
    assert _canonicalize_project_name("   ") == ""


def test_explicit_hint_is_stored_title_cased(monkeypatch) -> None:
    fake = _install_fake_db(monkeypatch)

    pid, name, reason, conf, needs_review = pr.resolve_project_for_client(
        client_id=1,
        text="please finish the perry project",
        explicit_project_name="perry project",
    )

    assert reason == "explicit_project_name"
    assert name == "Perry Project"
    assert any(r["id"] == pid and r["name"] == "Perry Project" for r in fake.rows)


def test_lowercase_hint_reuses_existing_titlecase_row(monkeypatch) -> None:
    """
    If a Title Case row already exists, a lowercase hint must reuse it,
    not create a duplicate.
    """
    fake = _install_fake_db(monkeypatch)
    fake.rows.append(
        {
            "id": 10,
            "client_id": 1,
            "name": "Perry Project",
            "description": None,
            "status": "active",
            "priority": None,
            "deadline": None,
        }
    )

    pid, name, reason, *_ = pr.resolve_project_for_client(
        client_id=1,
        text="quick update on perry project",
        explicit_project_name="perry project",
    )

    assert pid == 10
    assert name == "Perry Project"
    assert reason == "explicit_project_name"
    assert len(fake.rows) == 1


def test_fallback_is_title_cased_when_created(monkeypatch) -> None:
    fake = _install_fake_db(monkeypatch)

    pid, name, reason, *_ = pr.resolve_project_for_client(
        client_id=1,
        text="random unrelated text",
        explicit_project_name=None,
        fallback_project_name="general",
    )

    assert name == "General"
    assert reason == "fallback_created_general"
    assert any(r["id"] == pid and r["name"] == "General" for r in fake.rows)


def test_matched_project_name_in_text_is_reused_as_is(monkeypatch) -> None:
    """
    If a user already has projects, step 3 matches by substring in text.
    We deliberately need two projects so the single-project heuristic
    doesn't short-circuit the match.
    """
    fake = _install_fake_db(monkeypatch)
    fake.rows.append(
        {
            "id": 20,
            "client_id": 1,
            "name": "Perry Project",
            "description": None,
            "status": "active",
            "priority": None,
            "deadline": None,
        }
    )
    fake.rows.append(
        {
            "id": 21,
            "client_id": 1,
            "name": "Acme Project",
            "description": None,
            "status": "active",
            "priority": None,
            "deadline": None,
        }
    )

    pid, name, reason, *_ = pr.resolve_project_for_client(
        client_id=1,
        text="quick update on the perry project",
        explicit_project_name=None,
    )

    assert pid == 20
    assert name == "Perry Project"
    assert reason == "matched_project_name_in_text"
