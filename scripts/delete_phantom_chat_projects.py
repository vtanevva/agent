"""
One-off cleanup for phantom chat-origin projects.

Some older chat ingest code used a permissive regex that invented project
names such as ``"saturday at 15 project"`` or
``"add a task to finish lucient project"`` from generic user text. Those
rows ended up in SQLite as real projects even though the user never
intended them.

This script deletes the specific phantom ``projects`` rows that the user
has audited manually. It is intentionally an allow-list of ids rather
than a pattern match, so we cannot wipe something real by accident.

Side effects of deleting a ``projects`` row (per
``backend/storage/schema.sql``):

- ``project_context`` rows for that project: CASCADE delete.
- ``messages`` / ``tasks`` / ``follow_ups`` / ``calendar_events``:
  ``project_id`` is set to ``NULL``. The history stays; the wrong
  project link is just removed.

Usage::

    python scripts/delete_phantom_chat_projects.py           # dry run (default)
    python scripts/delete_phantom_chat_projects.py --apply   # perform deletes

Resolves the DB path from ``SQLITE_PATH`` (same as the backend) and falls
back to ``backend/storage/aivis.db``.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


# Audited in chat on 2026-04-24. Each entry is (id, expected_name).
# We assert the name matches before deleting, so re-running after new
# project rows were added to the same ids will simply fail safely.
PHANTOM_PROJECTS: list[tuple[int, str]] = [
    (7, "original message --- Project"),
    (9, "tomorrow project"),
    (10, "wednesday project"),
    (11, "saturday at 4 project"),
    (12, "saturday at 15 project"),
    (13, "add a task to finish lucient project"),
]


def _resolve_db_path() -> Path:
    raw = (os.getenv("SQLITE_PATH") or "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            # Same convention as backend/storage/sqlite_db.py: resolve
            # relative to the backend directory.
            p = Path(__file__).resolve().parents[1] / "backend" / raw
        return p.resolve()
    return (Path(__file__).resolve().parents[1] / "backend" / "storage" / "aivis.db").resolve()


def _summarize(conn: sqlite3.Connection, project_ids: list[int]) -> None:
    if not project_ids:
        return

    placeholders = ",".join("?" * len(project_ids))

    print("\n-- Impact summary --")
    for table, action in (
        ("project_context", "CASCADE delete"),
        ("messages", "project_id -> NULL"),
        ("tasks", "project_id -> NULL"),
        ("follow_ups", "project_id -> NULL"),
        ("calendar_events", "project_id -> NULL"),
    ):
        rows = conn.execute(
            f"SELECT project_id, COUNT(*) AS n FROM {table} "
            f"WHERE project_id IN ({placeholders}) GROUP BY project_id ORDER BY project_id",
            project_ids,
        ).fetchall()
        total = sum(r["n"] for r in rows)
        print(f"  {table:<16} {action:<20} -> {total} row(s)")
        for r in rows:
            print(f"      project_id={r['project_id']}  n={r['n']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually run the DELETE. Without this flag we only print the plan.",
    )
    args = parser.parse_args()

    db_path = _resolve_db_path()
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 2

    print(f"DB path: {db_path}")
    print(f"Dry run: {not args.apply}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        plan: list[tuple[int, str]] = []
        missing: list[tuple[int, str]] = []
        mismatched: list[tuple[int, str, str]] = []

        for project_id, expected_name in PHANTOM_PROJECTS:
            row = conn.execute(
                "SELECT id, name FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if row is None:
                missing.append((project_id, expected_name))
                continue
            actual_name = str(row["name"])
            if actual_name.strip().lower() != expected_name.strip().lower():
                mismatched.append((project_id, expected_name, actual_name))
                continue
            plan.append((project_id, actual_name))

        print("\n-- Plan --")
        if plan:
            for pid, name in plan:
                print(f"  DELETE projects id={pid}  name={name!r}")
        else:
            print("  (nothing to delete)")

        if missing:
            print("\n-- Already gone (skipped) --")
            for pid, name in missing:
                print(f"  project_id={pid}  expected={name!r}")

        if mismatched:
            print("\n-- Name mismatch (refusing to delete) --")
            for pid, expected, actual in mismatched:
                print(f"  project_id={pid}  expected={expected!r}  actual={actual!r}")
            print(
                "\nThose rows will NOT be touched. Re-audit manually before "
                "re-running this script."
            )

        _summarize(conn, [pid for pid, _ in plan])

        if not args.apply:
            print("\nDry run complete. Re-run with --apply to execute.")
            return 0

        if not plan:
            print("\nNothing to delete.")
            return 0

        print("\nApplying deletes...")
        try:
            conn.execute("BEGIN")
            for pid, _ in plan:
                conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        print(f"Deleted {len(plan)} project row(s).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
