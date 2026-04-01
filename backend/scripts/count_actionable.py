from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


def _scalar(cur: sqlite3.Cursor, q: str, params: tuple = ()) -> int:
    cur.execute(q, params)
    row = cur.fetchone()
    if not row:
        return 0
    try:
        return int(row[0] or 0)
    except Exception:
        return 0


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    db_path = Path(os.getenv("AIVIS_DB_PATH") or (repo_root / "backend" / "storage" / "aivis.db"))

    print(f"db_path={db_path}")
    if not db_path.exists():
        print("ERROR: database file not found")
        raise SystemExit(1)

    con = sqlite3.connect(str(db_path))
    cur = con.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    print("tables=", tables)

    if "messages" in tables:
        total = _scalar(cur, "SELECT COUNT(*) FROM messages")
        action_type = _scalar(
            cur,
            "SELECT COUNT(*) FROM messages WHERE classification_type IS NOT NULL AND UPPER(classification_type)=?",
            ("ACTION",),
        )
        print(f"messages_total={total}")
        print(f"messages_classification_type_ACTION={action_type}")

        has_action = 0
        cur.execute("SELECT classification_json FROM messages WHERE classification_json IS NOT NULL")
        for (cj,) in cur.fetchall():
            try:
                obj = json.loads(cj) if isinstance(cj, str) else cj
                if isinstance(obj, dict) and obj.get("has_action") is True:
                    has_action += 1
            except Exception:
                pass
        print(f"messages_classification_json_has_action_true={has_action}")

    if "tasks" in tables:
        total = _scalar(cur, "SELECT COUNT(*) FROM tasks")
        action_type = _scalar(
            cur,
            "SELECT COUNT(*) FROM tasks WHERE classification_type IS NOT NULL AND UPPER(classification_type)=?",
            ("ACTION",),
        )
        print(f"tasks_total={total}")
        print(f"tasks_classification_type_ACTION={action_type}")

    con.close()


if __name__ == "__main__":
    main()

