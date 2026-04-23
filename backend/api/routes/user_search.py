"""
Full-text style search across SQLite user data (messages, tasks, projects, calendar).
"""

from __future__ import annotations

import json
import re
from typing import Any

from flask import Blueprint, jsonify, request

from storage.sqlite_db import get_conn
from utils.logger import get_logger

log = get_logger("user_search")
user_search_bp = Blueprint("user_search", __name__)


def _safe_json_loads(v: Any) -> dict:
    if not v:
        return {}
    if isinstance(v, dict):
        return v
    if not isinstance(v, str):
        return {}
    try:
        obj = json.loads(v)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search_tokens(q: str) -> list[str]:
    raw = (q or "").strip().lower()
    if len(raw) < 2:
        return []
    parts = [p for p in re.split(r"\s+", raw) if len(p) >= 2]
    return parts[:8]


def _message_haystack(row: dict, payload: dict) -> str:
    bits = [
        str(row.get("text") or ""),
        str(row.get("user") or ""),
        str(row.get("channel") or ""),
        str(payload.get("subject") or ""),
        str(payload.get("snippet") or ""),
        str(payload.get("text") or ""),
        str(payload.get("from") or ""),
        str(payload.get("sender") or ""),
        json.dumps(payload, ensure_ascii=False) if payload else "",
    ]
    return " ".join(bits).lower()


def _workspace_for_payload(payload: dict) -> str:
    return str(
        payload.get("workspace_id")
        or payload.get("workspaceId")
        or payload.get("emailAddress")
        or ""
    ).strip().lower()


@user_search_bp.get("/api/search")
def user_search():
    """
    Search ingested messages, tasks, projects, project notes, and calendar titles.

    Query params:
      q — search string (min 2 chars after trim; multi-word = AND on tokens)
      user_id — optional; when it looks like an email, results are scoped to that mailbox/workspace
      limit — max hits per bucket (default 20, max 40)
    """
    q = (request.args.get("q") or "").strip()
    user_id = (request.args.get("user_id") or "").strip().lower()
    should_scope_workspace = bool(user_id and "@" in user_id)
    try:
        per_bucket = int(request.args.get("limit") or "20")
    except Exception:
        per_bucket = 20
    per_bucket = max(1, min(per_bucket, 40))

    tokens = _search_tokens(q)
    if not tokens:
        return (
            jsonify(
                {
                    "success": True,
                    "q": q,
                    "tokens": [],
                    "hits": {
                        "messages": [],
                        "tasks": [],
                        "projects": [],
                        "project_notes": [],
                        "calendar": [],
                    },
                }
            ),
            200,
        )

    # LIKE … ESCAPE '\' — bind one pattern per token per bucket
    def like_params(tokens_: list[str]) -> tuple[str, list[Any]]:
        clauses = []
        params: list[Any] = []
        for t in tokens_:
            esc = _like_escape(t)
            clauses.append(
                "LOWER(COALESCE(text, '') || ' ' || COALESCE(payload_json, '')) "
                "LIKE ? ESCAPE '\\'"
            )
            params.append(f"%{esc}%")
        return " AND ".join(clauses), params

    hits: dict[str, list[dict[str, Any]]] = {
        "messages": [],
        "tasks": [],
        "projects": [],
        "project_notes": [],
        "calendar": [],
    }

    with get_conn() as conn:
        # --- messages ---
        where_sql, bind = like_params(tokens)
        rows = conn.execute(
            f"""
            SELECT id, source, source_id, channel, ts, user, text, payload_json, created_at
            FROM messages
            WHERE {where_sql}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*bind, per_bucket * 4),
        ).fetchall()

        for r in rows:
            row = dict(r)
            payload = _safe_json_loads(row.get("payload_json"))
            if should_scope_workspace:
                ws = _workspace_for_payload(payload)
                if ws and ws != user_id:
                    continue
            hay = _message_haystack(row, payload)
            if not all(tok in hay for tok in tokens):
                continue
            src = row.get("source") or ""
            if src == "gmail":
                thread_id = payload.get("thread_id") or payload.get("threadId") or row.get("source_id")
            elif src == "slack":
                thread_id = (
                    payload.get("thread_ts")
                    or payload.get("threadTs")
                    or payload.get("ts")
                    or row.get("ts")
                )
            else:
                thread_id = payload.get("thread_id") or payload.get("thread_ts") or row.get("ts")
            thread_id = thread_id or row.get("source_id")
            subject = (payload.get("subject") or "").strip() or "(no subject)"
            from_v = (
                payload.get("from")
                or payload.get("sender")
                or row.get("user")
                or row.get("channel")
                or ""
            )
            snippet = (payload.get("snippet") or row.get("text") or payload.get("text") or "")[:220]
            hits["messages"].append(
                {
                    "kind": "message",
                    "id": row.get("id"),
                    "source": src,
                    "source_id": row.get("source_id"),
                    "thread_id": str(thread_id) if thread_id is not None else None,
                    "title": subject,
                    "subtitle": str(from_v).strip(),
                    "snippet": str(snippet).strip(),
                    "ts": row.get("ts") or row.get("created_at"),
                }
            )
            if len(hits["messages"]) >= per_bucket:
                break

        # --- tasks ---
        task_parts = [
            "LOWER("
            "COALESCE(t.title,'') || ' ' || COALESCE(t.description,'') || ' ' || "
            "COALESCE(t.classification_json,'') || ' ' || "
            "COALESCE(c.name,'') || ' ' || COALESCE(p.name,'')"
            ")"
        ]
        t_clauses = []
        t_bind: list[Any] = []
        for t in tokens:
            esc = _like_escape(t)
            t_clauses.append(f"{task_parts[0]} LIKE ? ESCAPE '\\'")
            t_bind.append(f"%{esc}%")
        t_where = " AND ".join(t_clauses)
        for tr in conn.execute(
            f"""
            SELECT t.id, t.title, t.description, t.source, t.source_id, t.created_at,
                   c.name AS client_name, p.name AS project_name
            FROM tasks t
            LEFT JOIN clients c ON c.id = t.client_id
            LEFT JOIN projects p ON p.id = t.project_id
            WHERE {t_where}
            ORDER BY t.id DESC
            LIMIT ?
            """,
            (*t_bind, per_bucket),
        ).fetchall():
            d = dict(tr)
            meta = " · ".join(
                x for x in (d.get("client_name") or "", d.get("project_name") or "") if x
            )
            hits["tasks"].append(
                {
                    "kind": "task",
                    "id": d.get("id"),
                    "title": d.get("title") or "(task)",
                    "subtitle": meta or (d.get("source") or ""),
                    "snippet": (d.get("description") or "")[:200],
                    "source": d.get("source"),
                    "source_id": d.get("source_id"),
                }
            )

        # --- projects ---
        p_clauses = []
        p_bind: list[Any] = []
        p_expr = "LOWER(COALESCE(p.name,'') || ' ' || COALESCE(p.description,'') || ' ' || COALESCE(c.name,''))"
        for t in tokens:
            esc = _like_escape(t)
            p_clauses.append(f"{p_expr} LIKE ? ESCAPE '\\'")
            p_bind.append(f"%{esc}%")
        p_where = " AND ".join(p_clauses)
        for pr in conn.execute(
            f"""
            SELECT p.id, p.name, p.description, c.name AS client_name
            FROM projects p
            JOIN clients c ON c.id = p.client_id
            WHERE {p_where}
            ORDER BY p.id DESC
            LIMIT ?
            """,
            (*p_bind, per_bucket),
        ).fetchall():
            d = dict(pr)
            hits["projects"].append(
                {
                    "kind": "project",
                    "id": d.get("id"),
                    "title": d.get("name") or "(project)",
                    "subtitle": d.get("client_name") or "",
                    "snippet": (d.get("description") or "")[:200],
                }
            )

        # --- project_context (saved notes / summary) ---
        n_clauses = []
        n_bind: list[Any] = []
        n_expr = (
            "LOWER(COALESCE(p.name,'') || ' ' || COALESCE(c.name,'') || ' ' || "
            "COALESCE(pc.summary,'') || ' ' || COALESCE(pc.current_status,'') || ' ' || "
            "COALESCE(pc.current_priorities,'') || ' ' || COALESCE(pc.blockers,'') || ' ' || "
            "COALESCE(pc.next_steps,''))"
        )
        for t in tokens:
            esc = _like_escape(t)
            n_clauses.append(f"{n_expr} LIKE ? ESCAPE '\\'")
            n_bind.append(f"%{esc}%")
        n_where = " AND ".join(n_clauses)
        for nr in conn.execute(
            f"""
            SELECT pc.project_id, p.name AS project_name, c.name AS client_name,
                   pc.summary, pc.current_status, pc.blockers, pc.next_steps
            FROM project_context pc
            JOIN projects p ON p.id = pc.project_id
            JOIN clients c ON c.id = p.client_id
            WHERE {n_where}
            ORDER BY pc.updated_at DESC
            LIMIT ?
            """,
            (*n_bind, per_bucket),
        ).fetchall():
            d = dict(nr)
            preview = " ".join(
                str(d.get(k) or "")
                for k in ("summary", "current_status", "blockers", "next_steps")
            ).strip()[:220]
            hits["project_notes"].append(
                {
                    "kind": "project_note",
                    "project_id": d.get("project_id"),
                    "title": d.get("project_name") or "Project",
                    "subtitle": d.get("client_name") or "",
                    "snippet": preview,
                }
            )

        # --- calendar ---
        cal_clauses = []
        cal_bind: list[Any] = []
        cal_expr = "LOWER(COALESCE(title,'') || ' ' || COALESCE(notes,''))"
        for t in tokens:
            esc = _like_escape(t)
            cal_clauses.append(f"{cal_expr} LIKE ? ESCAPE '\\'")
            cal_bind.append(f"%{esc}%")
        cal_where = " AND ".join(cal_clauses)
        for cr in conn.execute(
            f"""
            SELECT id, title, notes, start_at, end_at
            FROM calendar_events
            WHERE {cal_where}
            ORDER BY start_at DESC
            LIMIT ?
            """,
            (*cal_bind, per_bucket),
        ).fetchall():
            d = dict(cr)
            hits["calendar"].append(
                {
                    "kind": "calendar",
                    "id": d.get("id"),
                    "title": d.get("title") or "(event)",
                    "subtitle": f"{d.get('start_at') or ''} → {d.get('end_at') or ''}".strip(" →"),
                    "snippet": (d.get("notes") or "")[:180],
                }
            )

    total = sum(len(v) for v in hits.values())
    log.info("[user_search] q=%r tokens=%s total=%s", q, tokens, total)
    return jsonify({"success": True, "q": q, "tokens": tokens, "hits": hits, "total": total}), 200


__all__ = ["user_search_bp"]
