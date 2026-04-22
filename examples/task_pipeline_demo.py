"""
SQLite pipeline snapshot (replaces the old Mongo task_pipeline demo).

Run from repo root:
    python examples/task_pipeline_demo.py

Shows DB path and row counts for core tables. Ingestion / Grafik linking live in
``backend/services/unified_processor.py`` and ``backend/services/task_service.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for p in (str(ROOT), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("SQLITE_PATH", str(BACKEND / "storage" / "aivis.db"))


def main() -> None:
    from storage.sqlite_db import DB_PATH, get_conn, init_sqlite

    print("=" * 72)
    print("SQLite core snapshot (events / tasks / messages)")
    print("=" * 72)
    print(f"DB path: {DB_PATH}")

    init_sqlite()

    tables = ("events", "tasks", "messages", "metrics_events", "gmail_watch_state")
    with get_conn() as conn:
        for name in tables:
            try:
                row = conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()
                n = int(row["c"]) if row else 0
            except Exception as e:
                n = f"(skip: {e})"
            print(f"  {name}: {n}")

    print()
    print("Next: trace Gmail/Slack → SQLite in backend/services/unified_processor.py")
    print("=" * 72)


if __name__ == "__main__":
    main()
