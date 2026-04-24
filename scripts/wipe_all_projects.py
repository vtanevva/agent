"""
Full wipe of the ``projects`` table.

The user asked for a clean slate: delete every project row so the
system can rebuild its project catalogue from scratch with the new
Title Case normalization.

Blast radius (per ``backend/storage/schema.sql``):

- ``projects``: every row deleted.
- ``project_context``: CASCADE delete (context belongs to the project).
- ``messages`` / ``tasks`` / ``follow_ups`` / ``calendar_events``:
  ``project_id`` is set to ``NULL``. The records themselves are kept,
  just unlinked from projects so nothing is lost.
- ``clients``: untouched. Mailbox / chat / inbox routing still works.

Usage::

    python scripts/wipe_all_projects.py            # dry run (default)
    python scripts/wipe_all_projects.py --apply    # perform the wipe

Resolves the DB path from ``SQLITE_PATH`` (same as the backend) and
falls back to ``backend/storage/aivis.db``.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


def _resolve_db_path() -> Path:
    raw = (os.getenv("SQLITE_PATH") or "").strip()
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[1] / "backend" / raw
        return p.resolve()
    return (Path(__file__).resolve().parents[1] / "backend" / "storage" / "aivis.db").resolve()


def _summarize(conn: sqlite3.Connection) -> int:
    total = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
    print(f"\nprojects rows currently in DB: {total}")

    if total == 0:
        return 0

    print("\n-- Projects that would be deleted --")
    rows = conn.execute(
        """
        SELECT p.id, p.name, c.name AS client_name
        FROM projects p
        LEFT JOIN clients c ON c.id = p.client_id
        ORDER BY p.id
        """
    ).fetchall()
    for r in rows:
        print(f"  id={r['id']:<4}  client={r['client_name']!r:<20}  name={r['name']!r}")

    print("\n-- Side effects --")
    for table, action in (
        ("project_context", "CASCADE delete"),
        ("messages", "project_id -> NULL"),
        ("tasks", "project_id -> NULL"),
        ("follow_ups", "project_id -> NULL"),
        ("calendar_events", "project_id -> NULL"),
    ):
        n = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE project_id IS NOT NULL"
        ).fetchone()["n"]
        print(f"  {table:<16} {action:<20} -> {n} row(s) affected")

    return total


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

        total = _summarize(conn)

        if not args.apply:
            print("\nDry run complete. Re-run with --apply to execute.")
            return 0

        if total == 0:
            print("\nNothing to delete.")
            return 0

        print("\nApplying wipe...")
        try:
            conn.execute("BEGIN")
            # Single statement is enough: ON DELETE CASCADE handles
            # project_context, and ON DELETE SET NULL handles the rest.
            conn.execute("DELETE FROM projects")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        remaining = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
        print(f"Deleted {total} project row(s). Remaining: {remaining}.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
