import os
import sqlite3
from pathlib import Path
from datetime import datetime
import json
from collections import Counter
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "aivis.db"

_raw_db_path = (os.getenv("SQLITE_PATH") or "").strip()
if _raw_db_path:
    _p = Path(_raw_db_path)
    # Treat relative paths as relative to the backend directory (not the process CWD).
    DB_PATH = (_p if _p.is_absolute() else (BASE_DIR.parent / _p)).resolve()
else:
    DB_PATH = DEFAULT_DB_PATH.resolve()


def utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_sqlite():
    schema_path = BASE_DIR / "schema.sql"
    with get_conn() as conn:
        # If the DB already exists, SQLite won't apply CREATE TABLE changes.
        # Ensure critical columns exist before running schema/index creation.
        if _table_exists(conn, "tasks") and not _has_column(conn, "tasks", "grafik_task_id"):
            raise RuntimeError(
                f"SQLite schema mismatch at {DB_PATH}. Expected column tasks.grafik_task_id. "
                f"Delete the database file to recreate it from the current schema."
            )

        conn.executescript(schema_path.read_text(encoding="utf-8"))
        _migrate_sqlite(conn)
        conn.commit()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return bool(row)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _migrate_sqlite(conn: sqlite3.Connection) -> None:
    # Lightweight, additive migrations only.
    # Phase 4: track last meaningful project context update.
    if not _has_column(conn, "projects", "last_updated_at"):
        conn.execute("ALTER TABLE projects ADD COLUMN last_updated_at TEXT")

    # Local task lifecycle (replaces Grafik-managed state).
    if _table_exists(conn, "tasks"):
        if not _has_column(conn, "tasks", "status"):
            conn.execute("ALTER TABLE tasks ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
        if not _has_column(conn, "tasks", "completed_at"):
            conn.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")
        if not _has_column(conn, "tasks", "thread_id"):
            conn.execute("ALTER TABLE tasks ADD COLUMN thread_id TEXT")
        if not _has_column(conn, "tasks", "workspace_id"):
            conn.execute("ALTER TABLE tasks ADD COLUMN workspace_id TEXT")

    # Phase 11: metrics_events table (value tracking / observability)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          source TEXT NOT NULL,
          status TEXT NOT NULL,
          has_action INTEGER NOT NULL,
          reply_generated INTEGER NOT NULL,
          reply_mode TEXT,
          follow_up_created INTEGER NOT NULL,
          task_created INTEGER NOT NULL,
          task_linked INTEGER NOT NULL,
          project_memory_updated INTEGER NOT NULL,
          importance_level TEXT,
          importance_score INTEGER,
          has_schedule_signal INTEGER NOT NULL,
          time_pressure_level TEXT,
          duplicate_delivery INTEGER NOT NULL,
          error INTEGER NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_events_created_at ON metrics_events(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_events_source_status ON metrics_events(source, status)")

    # Gmail Pub/Sub watch state (baseline historyId per mailbox)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_watch_state (
          email_address TEXT PRIMARY KEY,
          last_history_id INTEGER,
          topic TEXT,
          label_ids_json TEXT,
          watch_expiration TEXT,
          watch_started_at TEXT,
          updated_at TEXT NOT NULL,
          note TEXT
        )
        """
    )

    # Gmail draft idempotency (prevent multiple drafts per message)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_draft_state (
          message_id TEXT PRIMARY KEY,
          source_id TEXT,
          thread_id TEXT,
          draft_id TEXT,
          status TEXT NOT NULL,
          error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )

    # Threads the user already replied to (hide answered items from tasks list).
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS thread_replies (
          source TEXT NOT NULL,
          workspace_id TEXT NOT NULL,
          thread_id TEXT NOT NULL,
          answered_at TEXT NOT NULL,
          sent_message_id TEXT,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (source, workspace_id, thread_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_thread_replies_source_workspace "
        "ON thread_replies(source, workspace_id)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profile_link (
          user_id TEXT PRIMARY KEY,
          gmail_address TEXT,
          slack_team_id TEXT,
          slack_user_id TEXT,
          updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_profile_link_gmail_lower
        ON profile_link(lower(trim(gmail_address)))
        WHERE gmail_address IS NOT NULL AND trim(gmail_address) != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_profile_link_slack_team
        ON profile_link(slack_team_id)
        WHERE slack_team_id IS NOT NULL AND trim(slack_team_id) != ''
        """
    )

    _migrate_clients_data_owner_key(conn)
    _backfill_client_data_owner_from_messages(conn)
    _migrate_calendar_events_data_owner_key(conn)


def _migrate_clients_data_owner_key(conn: sqlite3.Connection) -> None:
    """
    Replace global UNIQUE(name) on ``clients`` with per-user ``UNIQUE(data_owner_key, name)``.

    Old rows are bucketed under ``__unscoped__`` so existing installs keep one global namespace
    until new mail arrives for a keyed owner.
    """
    if not _table_exists(conn, "clients") or _has_column(conn, "clients", "data_owner_key"):
        return
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        BEGIN;
        CREATE TABLE clients__dataowner (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          data_owner_key TEXT NOT NULL DEFAULT '__unscoped__',
          description TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE (data_owner_key, name)
        );
        INSERT INTO clients__dataowner (id, name, data_owner_key, description, created_at, updated_at)
        SELECT id, name, '__unscoped__', description, created_at, updated_at FROM clients;
        DROP TABLE clients;
        ALTER TABLE clients__dataowner RENAME TO clients;
        COMMIT;
        PRAGMA foreign_keys = ON;
        """
    )


def _backfill_client_data_owner_from_messages(conn: sqlite3.Connection) -> None:
    """
    Move clients still bucketed as ``__unscoped__`` to the data-owner key implied by
    ``payload.app_user_id`` (and workspace hints) in stored messages, when a clear
    majority exists for that client.
    """
    if not _table_exists(conn, "messages") or not _table_exists(conn, "clients"):
        return
    if not _has_column(conn, "clients", "data_owner_key"):
        return
    ex = conn.execute(
        "SELECT 1 AS o FROM clients WHERE data_owner_key = '__unscoped__' LIMIT 1"
    ).fetchone()
    if not ex:
        return

    from services.data_owner_key import data_owner_key_for_ingest  # import after app path stable

    rows = conn.execute(
        "SELECT client_id, payload_json FROM messages WHERE client_id IS NOT NULL"
    ).fetchall()
    by_client: dict[int, list[str]] = {}
    for r in rows or []:
        cid = r["client_id"]
        if cid is None:
            continue
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            continue
        try:
            p = json.loads(r["payload_json"] or "{}")
        except Exception:
            p = {}
        if not isinstance(p, dict):
            p = {}
        uid = (p.get("app_user_id") or "").strip().lower()
        ws = (p.get("workspace_id") or p.get("workspaceId") or p.get("emailAddress") or "").strip().lower()
        if not uid and not ws:
            continue
        k = data_owner_key_for_ingest(app_user_id=uid or None, workspace_email=ws or None)
        if not k or k == "__unscoped__":
            continue
        by_client.setdefault(cid, []).append(k)

    for cid, keys in by_client.items():
        if not keys:
            continue
        most, n = Counter(keys).most_common(1)[0]
        if n < max(1, int(0.5 * len(keys)) + 1):
            continue
        try:
            conn.execute(
                """
                UPDATE clients
                SET data_owner_key = ?
                WHERE id = ? AND data_owner_key = '__unscoped__'
                """,
                (most, cid),
            )
        except Exception:
            pass


def _migrate_calendar_events_data_owner_key(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "calendar_events") or _has_column(conn, "calendar_events", "data_owner_key"):
        return
    conn.execute("ALTER TABLE calendar_events ADD COLUMN data_owner_key TEXT")
    try:
        conn.execute(
            """
            UPDATE calendar_events
            SET data_owner_key = (
                SELECT c.data_owner_key FROM clients c
                WHERE c.id = calendar_events.client_id
            )
            WHERE client_id IS NOT NULL
            """
        )
    except Exception:
        pass
    conn.execute(
        "UPDATE calendar_events SET data_owner_key = '__unscoped__' "
        "WHERE data_owner_key IS NULL"
    )


# ---------- Gmail watch state (Pub/Sub baseline) ----------
def get_gmail_watch_state(email_address: str) -> dict[str, Any] | None:
    email_address = (email_address or "").strip().lower()
    if not email_address:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM gmail_watch_state
            WHERE email_address = ?
            LIMIT 1
            """,
            (email_address,),
        ).fetchone()
    return dict(row) if row else None


def get_gmail_last_history_id(email_address: str) -> int | None:
    state = get_gmail_watch_state(email_address)
    if not state:
        return None
    v = state.get("last_history_id")
    try:
        return int(v) if v is not None else None
    except Exception:
        return None


def upsert_gmail_watch_state(
    *,
    email_address: str,
    last_history_id: int | None,
    topic: str | None = None,
    label_ids: list[str] | None = None,
    watch_expiration: str | None = None,
    note: str | None = None,
) -> None:
    email_address = (email_address or "").strip().lower()
    if not email_address:
        return

    now = utc_iso()
    label_ids_json = None
    try:
        label_ids_json = json.dumps(label_ids or [])
    except Exception:
        label_ids_json = "[]"

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO gmail_watch_state (
              email_address, last_history_id, topic, label_ids_json, watch_expiration, watch_started_at, updated_at, note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email_address) DO UPDATE SET
              last_history_id = excluded.last_history_id,
              topic = COALESCE(excluded.topic, gmail_watch_state.topic),
              label_ids_json = COALESCE(excluded.label_ids_json, gmail_watch_state.label_ids_json),
              watch_expiration = COALESCE(excluded.watch_expiration, gmail_watch_state.watch_expiration),
              watch_started_at = COALESCE(excluded.watch_started_at, gmail_watch_state.watch_started_at),
              updated_at = excluded.updated_at,
              note = COALESCE(excluded.note, gmail_watch_state.note)
            """,
            (
                email_address,
                int(last_history_id) if last_history_id is not None else None,
                (topic.strip() if isinstance(topic, str) and topic.strip() else None),
                label_ids_json,
                (str(watch_expiration).strip() if watch_expiration is not None else None),
                now,
                now,
                (str(note).strip() if note else None),
            ),
        )
        conn.commit()


def set_gmail_last_history_id(email_address: str, history_id: int, *, note: str | None = None) -> None:
    upsert_gmail_watch_state(email_address=email_address, last_history_id=int(history_id), note=note)


# ---------- Gmail draft idempotency ----------
def try_acquire_gmail_draft_lock(
    *,
    message_id: str,
    source_id: str,
    thread_id: str | None,
) -> bool:
    """
    Returns True if we acquired the lock for this message_id (first time),
    False if this message_id was already attempted.
    """
    message_id = (str(message_id or "").strip())
    if not message_id:
        return False

    now = utc_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO gmail_draft_state
              (message_id, source_id, thread_id, draft_id, status, error, created_at, updated_at)
            VALUES (?, ?, ?, NULL, 'started', NULL, ?, ?)
            """,
            (message_id, str(source_id or ""), (str(thread_id) if thread_id is not None else None), now, now),
        )
        conn.commit()
        return int(cur.rowcount or 0) == 1


def set_gmail_draft_result(
    *,
    message_id: str,
    draft_id: str | None,
    status: str,
    error: str | None = None,
) -> None:
    message_id = (str(message_id or "").strip())
    if not message_id:
        return
    now = utc_iso()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE gmail_draft_state
            SET draft_id = COALESCE(?, draft_id),
                status = ?,
                error = ?,
                updated_at = ?
            WHERE message_id = ?
            """,
            (str(draft_id).strip() if draft_id else None, str(status or "").strip(), (str(error) if error else None), now, message_id),
        )
        conn.commit()


# ---------- Thread replies (answered inbound threads) ----------
def mark_thread_answered(
    *,
    source: str,
    workspace_id: str,
    thread_id: str,
    answered_at: str | None = None,
    sent_message_id: str | None = None,
) -> None:
    """
    Record that the user replied in this thread. Used by the tasks list to
    hide items that no longer need action.

    Keeps the *latest* answered_at so a reply after a fresh inbound still wins.
    """
    source = (str(source or "").strip().lower())
    workspace_id = (str(workspace_id or "").strip().lower())
    thread_id = (str(thread_id or "").strip())
    if not source or not workspace_id or not thread_id:
        return

    ts = (str(answered_at).strip() if answered_at else "") or utc_iso()
    now = utc_iso()
    sid = (str(sent_message_id).strip() if sent_message_id else None)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO thread_replies
              (source, workspace_id, thread_id, answered_at, sent_message_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, workspace_id, thread_id) DO UPDATE SET
              answered_at = CASE
                WHEN excluded.answered_at > thread_replies.answered_at
                  THEN excluded.answered_at
                ELSE thread_replies.answered_at
              END,
              sent_message_id = COALESCE(excluded.sent_message_id, thread_replies.sent_message_id),
              updated_at = excluded.updated_at
            """,
            (source, workspace_id, thread_id, ts, sid, now),
        )
        conn.commit()


def get_answered_threads(
    *,
    source: str,
    workspace_id: str | None = None,
) -> dict[str, str]:
    """
    Returns a {thread_id: answered_at} map for the given source (optionally
    scoped by workspace/mailbox). Callers compare answered_at with the inbound
    message timestamp to decide whether to hide it.
    """
    source = (str(source or "").strip().lower())
    if not source:
        return {}

    params: list[Any] = [source]
    sql = "SELECT thread_id, answered_at FROM thread_replies WHERE source = ?"
    ws = (str(workspace_id).strip().lower() if workspace_id else "")
    if ws:
        sql += " AND workspace_id = ?"
        params.append(ws)

    out: dict[str, str] = {}
    with get_conn() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    for r in rows or []:
        tid = str(r["thread_id"] or "")
        if tid:
            out[tid] = str(r["answered_at"] or "")
    return out


# ---------- Clients / Projects / Context ----------
def create_client(
    name: str,
    description: str | None = None,
    *,
    data_owner_key: str = "__unscoped__",
) -> int:
    now = utc_iso()
    owner = (data_owner_key or "__unscoped__").strip() or "__unscoped__"
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO clients (name, data_owner_key, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(data_owner_key, name) DO UPDATE SET
              description = COALESCE(excluded.description, clients.description),
              updated_at = excluded.updated_at
            RETURNING id
            """,
            (name.strip(), owner, description, now, now),
        )
        row = cur.fetchone()
        conn.commit()
        return int(row["id"])


def get_client_by_name(name: str, data_owner_key: str | None = None) -> dict[str, Any] | None:
    owner = (data_owner_key if data_owner_key is not None else "__unscoped__").strip() or "__unscoped__"
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM clients
            WHERE lower(name) = lower(?) AND data_owner_key = ?
            LIMIT 1
            """,
            (name.strip(), owner),
        ).fetchone()
    return dict(row) if row else None


def create_project(
    client_id: int,
    name: str,
    description: str | None = None,
    status: str | None = "active",
    priority: str | None = None,
    deadline: str | None = None,
) -> int:
    now = utc_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO projects (
              client_id, name, description, status, priority, deadline, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_id, name) DO UPDATE SET
              description = COALESCE(excluded.description, projects.description),
              status = COALESCE(excluded.status, projects.status),
              priority = COALESCE(excluded.priority, projects.priority),
              deadline = COALESCE(excluded.deadline, projects.deadline),
              updated_at = excluded.updated_at
            RETURNING id
            """,
            (client_id, name.strip(), description, status, priority, deadline, now, now),
        )
        row = cur.fetchone()
        conn.commit()
        return int(row["id"])


def get_project_by_name(client_id: int, name: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM projects
            WHERE client_id = ? AND lower(name) = lower(?)
            LIMIT 1
            """,
            (client_id, name.strip()),
        ).fetchone()
    return dict(row) if row else None


def update_project_fields(*, project_id: int, fields_to_update: dict[str, Any]) -> None:
    """
    Minimal project updates. Only writes keys provided in fields_to_update.
    """
    if not fields_to_update:
        return

    allowed = {"description", "status", "priority", "deadline", "updated_at", "last_updated_at"}
    clean = {k: v for k, v in fields_to_update.items() if k in allowed}
    if not clean:
        return

    now = utc_iso()
    if "updated_at" not in clean:
        clean["updated_at"] = now

    cols = list(clean.keys())
    sets = ", ".join([f"{c} = ?" for c in cols])
    values = [clean[c] for c in cols] + [project_id]

    with get_conn() as conn:
        conn.execute(f"UPDATE projects SET {sets} WHERE id = ?", values)
        conn.commit()


def ensure_project_context_row(*, project_id: int, updated_by: str = "system") -> None:
    """
    Ensure a project_context row exists for project_id.
    """
    now = utc_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO project_context
            (project_id, key_contacts_json, important_links_json, updated_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, "[]", "[]", updated_by, now, now),
        )
        conn.commit()


def get_project_context_fields(project_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
              project_id,
              summary,
              current_status,
              current_priorities,
              blockers,
              next_steps,
              updated_by,
              created_at,
              updated_at
            FROM project_context
            WHERE project_id = ?
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def update_project_context_fields(
    *,
    project_id: int,
    fields_to_update: dict[str, Any],
    updated_by: str = "system",
) -> tuple[list[str], dict[str, Any] | None, dict[str, Any] | None]:
    """
    Update only changed, supported project_context fields.

    Returns (changed_fields, before, after).
    """
    supported = {"summary", "current_status", "current_priorities", "blockers", "next_steps"}
    requested = {k: v for k, v in (fields_to_update or {}).items() if k in supported}
    if not requested:
        before = get_project_context_fields(project_id)
        return [], before, before

    ensure_project_context_row(project_id=project_id, updated_by=updated_by)
    before = get_project_context_fields(project_id) or {}

    changed: dict[str, Any] = {}
    changed_fields: list[str] = []

    for k, v in requested.items():
        if v is None:
            continue
        new_val = str(v).strip()
        old_val = str(before.get(k) or "").strip()
        if new_val and new_val != old_val:
            changed[k] = new_val
            changed_fields.append(k)

    if not changed_fields:
        return [], before, before

    now = utc_iso()
    cols = list(changed.keys()) + ["updated_by", "updated_at"]
    sets = ", ".join([f"{c} = ?" for c in cols])
    values = [changed[c] for c in changed.keys()] + [updated_by, now, project_id]

    with get_conn() as conn:
        conn.execute(f"UPDATE project_context SET {sets} WHERE project_id = ?", values)
        conn.commit()

    # Phase 4: project-level last_updated_at marker
    update_project_fields(project_id=project_id, fields_to_update={"last_updated_at": now})

    after = get_project_context_fields(project_id) or {}
    return changed_fields, before, after

def upsert_project_context(
    *,
    project_id: int,
    summary: str | None = None,
    current_status: str | None = None,
    current_priorities: str | None = None,
    blockers: str | None = None,
    next_steps: str | None = None,
    key_contacts: list[str] | None = None,
    important_links: list[str] | None = None,
    updated_by: str = "system",
) -> None:
    now = utc_iso()
    key_contacts_json = json.dumps(key_contacts or [], ensure_ascii=False)
    important_links_json = json.dumps(important_links or [], ensure_ascii=False)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO project_context (
              project_id, summary, current_status, current_priorities,
              blockers, next_steps, key_contacts_json, important_links_json,
              updated_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
              summary = COALESCE(excluded.summary, project_context.summary),
              current_status = COALESCE(excluded.current_status, project_context.current_status),
              current_priorities = COALESCE(excluded.current_priorities, project_context.current_priorities),
              blockers = COALESCE(excluded.blockers, project_context.blockers),
              next_steps = COALESCE(excluded.next_steps, project_context.next_steps),
              key_contacts_json = CASE
                WHEN excluded.key_contacts_json = '[]' THEN project_context.key_contacts_json
                ELSE excluded.key_contacts_json
              END,
              important_links_json = CASE
                WHEN excluded.important_links_json = '[]' THEN project_context.important_links_json
                ELSE excluded.important_links_json
              END,
              updated_by = excluded.updated_by,
              updated_at = excluded.updated_at
            """,
            (
                project_id,
                summary,
                current_status,
                current_priorities,
                blockers,
                next_steps,
                key_contacts_json,
                important_links_json,
                updated_by,
                now,
                now,
            ),
        )
        conn.commit()


def get_project_context(project_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
              pc.*,
              p.name AS project_name,
              p.status AS project_status,
              p.priority AS project_priority,
              p.deadline AS project_deadline,
              c.id AS client_id,
              c.name AS client_name
            FROM project_context pc
            JOIN projects p ON p.id = pc.project_id
            JOIN clients c ON c.id = p.client_id
            WHERE pc.project_id = ?
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()

    if not row:
        return None

    data = dict(row)
    for key in ("key_contacts_json", "important_links_json"):
        try:
            data[key] = json.loads(data[key]) if data.get(key) else []
        except Exception:
            data[key] = []
    return data


def create_calendar_event(
    *,
    title: str,
    start_at: str,
    end_at: str,
    source: str,
    external_id: str | None = None,
    timezone: str | None = None,
    data_owner_key: str | None = None,
    client_id: int | None = None,
    project_id: int | None = None,
    notes: str | None = None,
) -> int:
    now = utc_iso()
    owner = (data_owner_key or "__unscoped__").strip() or "__unscoped__"
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO calendar_events (
              external_id, title, start_at, end_at, timezone, source,
              data_owner_key, client_id, project_id, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                external_id,
                title,
                start_at,
                end_at,
                timezone,
                source,
                owner,
                client_id,
                project_id,
                notes,
                now,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_upcoming_calendar_events(
    limit: int = 20, *, data_owner_key: str | None = None
) -> list[dict[str, Any]]:
    owner = (data_owner_key or "").strip() or None
    with get_conn() as conn:
        if owner is not None:
            rows = conn.execute(
                """
                SELECT *
                FROM calendar_events
                WHERE data_owner_key = ?
                ORDER BY start_at ASC
                LIMIT ?
                """,
                (owner, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM calendar_events
                ORDER BY start_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def list_calendar_events_in_range(
    time_min_iso: str,
    time_max_iso: str,
    limit: int = 500,
    *,
    data_owner_key: str | None = None,
) -> list[dict[str, Any]]:
    """Calendar rows overlapping [time_min, time_max) in ISO UTC string form."""
    owner = (data_owner_key or "").strip() or None
    with get_conn() as conn:
        if owner is not None:
            rows = conn.execute(
                """
                SELECT *
                FROM calendar_events
                WHERE end_at > ? AND start_at < ? AND data_owner_key = ?
                ORDER BY start_at ASC
                LIMIT ?
                """,
                (time_min_iso, time_max_iso, owner, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM calendar_events
                WHERE end_at > ? AND start_at < ?
                ORDER BY start_at ASC
                LIMIT ?
                """,
                (time_min_iso, time_max_iso, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def get_project_by_id(project_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM projects
            WHERE id = ?
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def list_projects_for_client(client_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              id,
              client_id,
              name,
              description,
              status,
              priority,
              deadline,
              created_at,
              updated_at
            FROM projects
            WHERE client_id = ?
            ORDER BY name ASC
            """,
            (client_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_all_projects_with_clients(*, data_owner_key: str | None = None) -> list[dict[str, Any]]:
    """All projects with their client name, ordered by client then project.

    If ``data_owner_key`` is set, only clients for that app user / mailbox are included.
    """
    owner = (data_owner_key or "").strip() or None
    with get_conn() as conn:
        if owner is not None:
            rows = conn.execute(
                """
                SELECT
                  p.id,
                  p.client_id,
                  p.name,
                  p.description,
                  p.status,
                  p.priority,
                  p.deadline,
                  p.created_at,
                  p.updated_at,
                  p.last_updated_at,
                  c.name AS client_name
                FROM projects p
                JOIN clients c ON c.id = p.client_id
                WHERE c.data_owner_key = ?
                ORDER BY c.name ASC, p.name ASC
                """,
                (owner,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                  p.id,
                  p.client_id,
                  p.name,
                  p.description,
                  p.status,
                  p.priority,
                  p.deadline,
                  p.created_at,
                  p.updated_at,
                  p.last_updated_at,
                  c.name AS client_name
                FROM projects p
                JOIN clients c ON c.id = p.client_id
                ORDER BY c.name ASC, p.name ASC
                """
            ).fetchall()
    return [dict(r) for r in rows]


def list_projects_overview(
    *, tasks_per_project: int = 30, data_owner_key: str | None = None
) -> list[dict[str, Any]]:
    """
    Projects with optional SQLite project_context and recent tasks for each.
    Intended for internal dashboards (GET /debug/sql/projects-overview).
    """
    lim = max(1, min(int(tasks_per_project), 100))
    rows = list_all_projects_with_clients(data_owner_key=data_owner_key)
    out: list[dict[str, Any]] = []
    for p in rows:
        pid = int(p["id"])
        ctx = get_project_context(pid)
        tasks = get_recent_tasks_for_project(pid, limit=lim)
        slim_tasks: list[dict[str, Any]] = []
        for t in tasks:
            slim_tasks.append(
                {
                    "id": int(t["id"]),
                    "title": t.get("title") or "",
                    "source": t.get("source") or "",
                    "classification_type": t.get("classification_type") or "",
                    "created_at": t.get("created_at") or "",
                }
            )
        entry = dict(p)
        entry["context"] = ctx
        entry["tasks"] = slim_tasks
        out.append(entry)
    return out


# ---------- Profile link (Expo user ↔ Gmail / Slack for ingest app_user_id) ----------
def get_gmail_for_app_user(user_id: str) -> str | None:
    """Return the Gmail address stored in ``profile_link`` for this app login, if any."""
    uid = (user_id or "").strip().lower()
    if not uid:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT gmail_address FROM profile_link
            WHERE lower(trim(user_id)) = ?
            LIMIT 1
            """,
            (uid,),
        ).fetchone()
    if not row or not row["gmail_address"]:
        return None
    out = str(row["gmail_address"]).strip().lower()
    return out or None


def upsert_profile_link_gmail(*, user_id: str, gmail_address: str) -> None:
    """Record which app user owns a Gmail mailbox (used by Pub/Sub + action-items scoping)."""
    uid = (user_id or "").strip().lower()
    em = (gmail_address or "").strip().lower()
    if not uid or not em:
        return
    now = utc_iso()
    with get_conn() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute(
                """
                UPDATE profile_link
                SET gmail_address = NULL
                WHERE lower(trim(gmail_address)) = ? AND lower(trim(user_id)) <> ?
                """,
                (em, uid),
            )
            conn.execute(
                """
                INSERT INTO profile_link (user_id, gmail_address, slack_team_id, slack_user_id, updated_at)
                VALUES (?, ?, NULL, NULL, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  gmail_address = excluded.gmail_address,
                  updated_at = excluded.updated_at
                """,
                (uid, em, now),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def upsert_profile_link_slack(
    *,
    user_id: str,
    slack_team_id: str,
    slack_user_id: str | None = None,
) -> None:
    """Link a Slack workspace (team id) to an app user. Clears the same team from other profiles."""
    uid = (user_id or "").strip().lower()
    tid = (slack_team_id or "").strip()
    if not uid or not tid:
        return
    sid = (slack_user_id or "").strip() or None
    now = utc_iso()
    with get_conn() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute(
                """
                UPDATE profile_link
                SET slack_team_id = NULL, slack_user_id = NULL
                WHERE trim(slack_team_id) = ? AND lower(trim(user_id)) <> ?
                """,
                (tid, uid),
            )
            conn.execute(
                """
                INSERT INTO profile_link (user_id, gmail_address, slack_team_id, slack_user_id, updated_at)
                VALUES (?, NULL, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  slack_team_id = excluded.slack_team_id,
                  slack_user_id = excluded.slack_user_id,
                  updated_at = excluded.updated_at
                """,
                (uid, tid, sid, now),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_user_id_for_gmail_address(gmail_address: str) -> str | None:
    addr = (gmail_address or "").strip().lower()
    if not addr:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT user_id FROM profile_link
            WHERE lower(trim(gmail_address)) = ?
            LIMIT 1
            """,
            (addr,),
        ).fetchone()
    return str(row["user_id"]).strip().lower() if row else None


def resolve_slack_app_user_id(team_id: str, slack_event_user: str) -> str | None:
    """
    Map a Slack team + message author to an app user_id.

    - Single profile linked to this team → all events stamp to that user.
    - Multiple profiles on the same team → stamp only when exactly one profile's
      ``slack_user_id`` matches ``slack_event_user`` (Slack member id of the sender).
    """
    team = (team_id or "").strip()
    su = (slack_event_user or "").strip()
    if not team:
        return None
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT user_id, slack_user_id FROM profile_link
            WHERE trim(slack_team_id) = ?
            """,
            (team,),
        ).fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return str(rows[0]["user_id"]).strip().lower()
    if not su:
        return None
    hits = [r for r in rows if (r["slack_user_id"] or "").strip() == su]
    if len(hits) == 1:
        return str(hits[0]["user_id"]).strip().lower()
    return None


# ---------- Messages (dedup + context) ----------
def insert_message_if_new(
    *,
    source: str,
    source_id: str,
    channel: str,
    ts: str,
    user: str,
    text: str,
    payload: dict,
) -> tuple[bool, int | None]:
    now = utc_iso()
    payload_json = json.dumps(payload, ensure_ascii=False)

    try:
        with get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages
                (source, source_id, channel, ts, user, text, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (source, source_id, channel, str(ts), user, text, payload_json, now),
            )
            conn.commit()
            return True, int(cur.lastrowid)
    except sqlite3.IntegrityError:
        return False, None


def attach_message_context(
    *,
    message_id: int,
    client_id: int | None = None,
    project_id: int | None = None,
    classification_type: str | None = None,
    classification: dict | None = None,
) -> None:
    classification_json = (
        json.dumps(classification, ensure_ascii=False) if classification is not None else None
    )
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE messages
            SET client_id = COALESCE(?, client_id),
                project_id = COALESCE(?, project_id),
                classification_type = COALESCE(?, classification_type),
                classification_json = COALESCE(?, classification_json)
            WHERE id = ?
            """,
            (client_id, project_id, classification_type, classification_json, message_id),
        )
        conn.commit()


def get_message_payload(*, source: str, source_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT payload_json
            FROM messages
            WHERE source = ? AND source_id = ?
            LIMIT 1
            """,
            (source, source_id),
        ).fetchone()

    if not row:
        return None

    payload_json = row["payload_json"]
    if not payload_json:
        return None

    try:
        return json.loads(payload_json)
    except Exception:
        return None


def get_message_context_for_source_id(*, source: str, source_id: str) -> dict[str, Any] | None:
    """
    Lightweight message context lookup for duplicate deliveries.
    """
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
              id,
              source,
              source_id,
              client_id,
              project_id,
              classification_type,
              created_at
            FROM messages
            WHERE source = ? AND source_id = ?
            LIMIT 1
            """,
            (source, source_id),
        ).fetchone()
    return dict(row) if row else None


def get_recent_messages_for_project(project_id: int, limit: int = 5) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              id,
              source,
              source_id,
              ts,
              text,
              classification_type,
              classification_json,
              created_at
            FROM messages
            WHERE project_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_messages_for_client(client_id: int, limit: int = 5) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              id,
              source,
              source_id,
              ts,
              text,
              classification_type,
              classification_json,
              created_at
            FROM messages
            WHERE client_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (client_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- Events (audit log) ----------
def log_event(
    *,
    source: str,
    source_id: str,
    step: str,
    status: str,
    data: dict | None = None,
) -> None:
    now = utc_iso()
    data_json = json.dumps(data, ensure_ascii=False) if data is not None else None
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO events (source, source_id, step, status, data_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (source, source_id, step, status, data_json, now),
        )
        conn.commit()


# ---------- Tasks ----------
def upsert_task(
    *,
    source: str,
    source_id: str,
    grafik_task_id: str,
    title: str,
    description: str,
    classification: dict,
    client_id: int | None = None,
    project_id: int | None = None,
    thread_id: str | None = None,
    workspace_id: str | None = None,
) -> int | None:
    """
    Upsert a local task row. ``grafik_task_id`` is kept as a legacy column name
    (the real ID since Grafik was removed is a local ``aivis-local-<hex>`` UUID).
    Returns the integer row id.
    """
    now = utc_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO tasks (
              source, source_id, grafik_task_id,
              client_id, project_id,
              title, description,
              classification_type, classification_json,
              created_at, updated_at,
              status, thread_id, workspace_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            ON CONFLICT(source, source_id) DO UPDATE SET
              grafik_task_id = excluded.grafik_task_id,
              client_id = COALESCE(excluded.client_id, tasks.client_id),
              project_id = COALESCE(excluded.project_id, tasks.project_id),
              title = excluded.title,
              description = excluded.description,
              classification_type = excluded.classification_type,
              classification_json = excluded.classification_json,
              thread_id = COALESCE(excluded.thread_id, tasks.thread_id),
              workspace_id = COALESCE(excluded.workspace_id, tasks.workspace_id),
              updated_at = excluded.updated_at
            """,
            (
                source,
                source_id,
                grafik_task_id,
                client_id,
                project_id,
                title,
                description,
                classification.get("type", "ACTION"),
                json.dumps(classification, ensure_ascii=False),
                now,
                now,
                (thread_id.strip() if isinstance(thread_id, str) and thread_id.strip() else None),
                (workspace_id.strip().lower() if isinstance(workspace_id, str) and workspace_id.strip() else None),
            ),
        )
        row = conn.execute(
            "SELECT id FROM tasks WHERE source = ? AND source_id = ? LIMIT 1",
            (source, source_id),
        ).fetchone()
        conn.commit()
    return int(row["id"]) if row else None


def list_local_tasks(
    *,
    limit: int = 200,
    include_completed: bool = False,
    data_owner_key: str | None = None,
    app_user_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Tasks for the home/week UI (no Grafik, all local).

    When ``data_owner_key`` is set, restrict to that owner's clients, plus
    unscoped tasks for the same mailbox (Gmail) or chat session prefix.
    """
    filters: list[str] = []
    if not include_completed:
        filters.append("COALESCE(t.status, 'pending') != 'completed'")
    extra_params: list[Any] = []
    if data_owner_key is not None:
        dk = (data_owner_key or "__unscoped__").strip() or "__unscoped__"
        ors = ["c.data_owner_key = ?"]
        extra_params.append(dk)
        uid = (app_user_id or "").strip().lower()
        mbox = uid if "@" in uid else (get_gmail_for_app_user(uid) or "").strip().lower()
        if mbox:
            ors.append(
                "(t.client_id IS NULL AND t.source = 'gmail' AND lower(trim(coalesce(t.workspace_id, ''))) = ?)"
            )
            extra_params.append(mbox)
        # Chat tasks use ``source_id = f"chat_task:{session_id}:{uuid}"`` where
        # ``session_id`` is ``{app_user_id}-{6 random base36 chars}`` (see
        # ``frontend/src/config/api.js`` ``genSession``). Match that prefix for
        # any ``client_id`` — Home already scopes the same way; without this,
        # rows linked to Inbox but whose ``clients.data_owner_key`` is missing
        # or stale never appear on the week view.
        if uid:
            ors.append(
                "(t.source IN ('chat', 'chat_task') AND t.source_id LIKE ? ESCAPE '\\')"
            )
            extra_params.append(
                "chat_task:" + uid.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "-%"
            )
        filters.append("(" + " OR ".join(ors) + ")")
    where_sql = ("WHERE " + " AND ".join(filters)) if filters else ""

    lim = int(max(1, min(limit, 500)))
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT
              t.id, t.source, t.source_id, t.grafik_task_id,
              t.client_id, t.project_id, t.thread_id, t.workspace_id,
              t.title, t.description,
              t.classification_type, t.classification_json,
              COALESCE(t.status, 'pending') AS status,
              t.completed_at,
              t.created_at, t.updated_at,
              c.name AS client_name,
              p.name AS project_name
            FROM tasks t
            LEFT JOIN clients c ON c.id = t.client_id
            LEFT JOIN projects p ON p.id = t.project_id
            {where_sql}
            ORDER BY t.id DESC
            LIMIT ?
            """,
            (*extra_params, lim),
        ).fetchall()
    return [dict(r) for r in rows]


def get_task_by_id(task_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
              t.id, t.source, t.source_id, t.grafik_task_id,
              t.client_id, t.project_id, t.thread_id, t.workspace_id,
              t.title, t.description,
              t.classification_type, t.classification_json,
              COALESCE(t.status, 'pending') AS status,
              t.completed_at,
              t.created_at, t.updated_at
            FROM tasks
            WHERE id = ?
            LIMIT 1
            """,
            (int(task_id),),
        ).fetchone()
    return dict(row) if row else None


def complete_local_task(task_id: int) -> dict[str, Any] | None:
    now = utc_iso()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE tasks
               SET status = 'completed',
                   completed_at = ?,
                   updated_at = ?
             WHERE id = ?
            """,
            (now, now, int(task_id)),
        )
        conn.commit()
    return get_task_by_id(task_id)


def list_recent_tasks(
    limit: int = 20,
    *,
    data_owner_key: str | None = None,
    app_user_id: str | None = None,
) -> list[dict[str, Any]]:
    if data_owner_key is not None:
        return list_local_tasks(
            limit=limit,
            include_completed=True,
            data_owner_key=data_owner_key,
            app_user_id=app_user_id,
        )

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              t.id, t.source, t.source_id, t.grafik_task_id,
              t.client_id, t.project_id,
              t.title, t.classification_type, t.classification_json,
              t.created_at, t.updated_at,
              c.name AS client_name,
              p.name AS project_name
            FROM tasks t
            LEFT JOIN clients c ON c.id = t.client_id
            LEFT JOIN projects p ON p.id = t.project_id
            ORDER BY t.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_tasks_for_project(project_id: int, limit: int = 10) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              id,
              source,
              source_id,
              grafik_task_id,
              client_id,
              project_id,
              title,
              description,
              classification_type,
              classification_json,
              created_at,
              updated_at
            FROM tasks
            WHERE project_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_tasks_for_client(client_id: int, limit: int = 10) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              id,
              source,
              source_id,
              grafik_task_id,
              client_id,
              project_id,
              title,
              description,
              classification_type,
              classification_json,
              created_at,
              updated_at
            FROM tasks
            WHERE client_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (client_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- Follow-ups ----------
def insert_follow_up_if_new(
    *,
    source: str,
    source_id: str,
    type: str,
    status: str = "open",
    due_at: str | None = None,
    client_id: int | None = None,
    project_id: int | None = None,
) -> tuple[bool, int | None]:
    now = utc_iso()
    try:
        with get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO follow_ups
                (source, source_id, client_id, project_id, type, status, due_at, created_at, updated_at, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (source, source_id, client_id, project_id, type, status, due_at, now, now),
            )
            conn.commit()
            return True, int(cur.lastrowid)
    except sqlite3.IntegrityError:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM follow_ups
                WHERE source = ? AND source_id = ?
                LIMIT 1
                """,
                (source, source_id),
            ).fetchone()
        return False, int(row["id"]) if row else None


def get_open_follow_ups_for_project(project_id: int, limit: int = 5) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              id,
              type,
              status,
              due_at,
              source,
              source_id,
              created_at
            FROM follow_ups
            WHERE project_id = ? AND status = 'open'
            ORDER BY
              CASE WHEN due_at IS NULL THEN 1 ELSE 0 END ASC,
              due_at ASC,
              id DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_open_follow_ups_for_client(client_id: int, limit: int = 5) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              id,
              type,
              status,
              due_at,
              source,
              source_id,
              created_at
            FROM follow_ups
            WHERE client_id = ? AND status = 'open'
            ORDER BY
              CASE WHEN due_at IS NULL THEN 1 ELSE 0 END ASC,
              due_at ASC,
              id DESC
            LIMIT ?
            """,
            (client_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- Metrics events (Phase 11) ----------
def insert_metrics_event(event: dict[str, Any]) -> int:
    now = utc_iso()
    e = event or {}
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO metrics_events (
              created_at,
              source, status,
              has_action,
              reply_generated, reply_mode,
              follow_up_created,
              task_created,
              task_linked,
              project_memory_updated,
              importance_level, importance_score,
              has_schedule_signal, time_pressure_level,
              duplicate_delivery,
              error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                e.get("created_at") or now,
                str(e.get("source") or ""),
                str(e.get("status") or ""),
                int(bool(e.get("has_action"))),
                int(bool(e.get("reply_generated"))),
                e.get("reply_mode"),
                int(bool(e.get("follow_up_created"))),
                int(bool(e.get("task_created"))),
                int(bool(e.get("task_linked"))),
                int(bool(e.get("project_memory_updated"))),
                e.get("importance_level"),
                e.get("importance_score"),
                int(bool(e.get("has_schedule_signal"))),
                e.get("time_pressure_level"),
                int(bool(e.get("duplicate_delivery"))),
                int(bool(e.get("error"))),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_metrics_summary() -> dict[str, Any]:
    """
    Returns aggregated counters and breakdowns from metrics_events.
    """
    with get_conn() as conn:
        totals = conn.execute(
            """
            SELECT
              COUNT(*) AS messages_processed,
              SUM(CASE WHEN duplicate_delivery = 1 THEN 1 ELSE 0 END) AS duplicates,
              SUM(CASE WHEN error = 1 THEN 1 ELSE 0 END) AS errors,
              SUM(CASE WHEN task_created = 1 THEN 1 ELSE 0 END) AS tasks_created,
              SUM(CASE WHEN task_linked = 1 THEN 1 ELSE 0 END) AS tasks_linked,
              SUM(CASE WHEN follow_up_created = 1 THEN 1 ELSE 0 END) AS follow_ups_created,
              SUM(CASE WHEN project_memory_updated = 1 THEN 1 ELSE 0 END) AS project_memory_updates,
              SUM(CASE WHEN reply_generated = 1 THEN 1 ELSE 0 END) AS replies_generated
            FROM metrics_events
            """
        ).fetchone()

        importance_rows = conn.execute(
            """
            SELECT importance_level, COUNT(*) AS n
            FROM metrics_events
            WHERE importance_level IS NOT NULL AND importance_level != ''
            GROUP BY importance_level
            """
        ).fetchall()

        pressure_rows = conn.execute(
            """
            SELECT time_pressure_level, COUNT(*) AS n
            FROM metrics_events
            WHERE time_pressure_level IS NOT NULL AND time_pressure_level != ''
            GROUP BY time_pressure_level
            """
        ).fetchall()

        with_schedule = conn.execute(
            """
            SELECT SUM(CASE WHEN has_schedule_signal = 1 THEN 1 ELSE 0 END) AS n
            FROM metrics_events
            """
        ).fetchone()

    totals_dict = dict(totals) if totals else {}
    for k in list(totals_dict.keys()):
        totals_dict[k] = int(totals_dict[k] or 0)

    importance_breakdown: dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for r in importance_rows or []:
        lvl = str(r["importance_level"] or "").strip().lower()
        if lvl in importance_breakdown:
            importance_breakdown[lvl] = int(r["n"] or 0)

    with_schedule_n = 0
    if with_schedule is not None:
        try:
            with_schedule_n = int(with_schedule["n"] or 0)
        except Exception:
            try:
                with_schedule_n = int(dict(with_schedule).get("n") or 0)
            except Exception:
                with_schedule_n = 0

    scheduling_breakdown: dict[str, int] = {
        "with_schedule_signal": with_schedule_n,
        "none": 0,
        "low": 0,
        "medium": 0,
        "high": 0,
    }
    for r in pressure_rows or []:
        lvl = str(r["time_pressure_level"] or "").strip().lower()
        if lvl in {"none", "low", "medium", "high"}:
            scheduling_breakdown[lvl] = int(r["n"] or 0)

    return {
        "totals": totals_dict,
        "importance_breakdown": importance_breakdown,
        "scheduling_breakdown": scheduling_breakdown,
    }