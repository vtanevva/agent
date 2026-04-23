"""
Search: SQLite (indexed pipeline data) plus live Gmail + Slack inbox search when OAuth/tokens exist.
Outlook/Graph is not wired yet — returns an empty bucket until Microsoft auth is implemented.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
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


def _gmail_query_from_tokens(tokens: list[str]) -> str:
    """Gmail `q` syntax: space-separated terms are ANDed."""
    return " ".join(t.strip() for t in tokens if t.strip())


def _search_gmail_live(*, gmail_q: str, max_results: int) -> list[dict[str, Any]]:
    """Live Gmail search via users.messages.list (requires token.json + credentials)."""
    out: list[dict[str, Any]] = []
    if not gmail_q:
        return out
    try:
        from services.gmail_auth import get_gmail_service
    except Exception as e:
        log.warning("[user_search] gmail import failed: %s", e)
        return out
    try:
        service = get_gmail_service()
    except Exception as e:
        log.info("[user_search] gmail live skipped (not signed in?): %s", e)
        return out
    try:
        listed = (
            service.users()
            .messages()
            .list(userId="me", q=gmail_q, maxResults=max(1, min(max_results, 25)))
            .execute()
        )
    except Exception as e:
        log.warning("[user_search] gmail list failed: %s", e)
        return out
    for m in listed.get("messages") or []:
        mid = m.get("id")
        if not mid:
            continue
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=mid, format="metadata", metadataHeaders=["Subject", "From", "Date"])
                .execute()
            )
        except Exception:
            continue
        headers = {str(h.get("name", "")).lower(): (h.get("value") or "") for h in (msg.get("payload") or {}).get("headers") or []}
        subject = (headers.get("subject") or "(no subject)").strip()
        from_h = (headers.get("from") or "").strip()
        snippet = (msg.get("snippet") or "").strip()[:240]
        thread_id = msg.get("threadId") or m.get("threadId")
        out.append(
            {
                "kind": "gmail_live",
                "message_id": mid,
                "thread_id": str(thread_id) if thread_id else None,
                "title": subject,
                "subtitle": from_h,
                "snippet": snippet,
            }
        )
        if len(out) >= max_results:
            break
    return out


def _search_slack_live(*, query: str, max_results: int) -> list[dict[str, Any]]:
    """
    Slack search.messages (bot needs search:read on the installed app).
    Uses the same SLACK_BOT_TOKEN as interactive routes.
    """
    out: list[dict[str, Any]] = []
    tok = (os.getenv("SLACK_BOT_TOKEN") or "").strip()
    if not tok or not (query or "").strip():
        return out
    try:
        r = requests.get(
            "https://slack.com/api/search.messages",
            headers={"Authorization": f"Bearer {tok}"},
            params={"query": query.strip(), "count": max(1, min(max_results, 25))},
            timeout=25,
        )
        data = r.json() if r.content else {}
    except Exception as e:
        log.warning("[user_search] slack search request failed: %s", e)
        return out
    if not data.get("ok"):
        log.info("[user_search] slack search not ok: %s", data.get("error"))
        return out
    matches = (data.get("messages") or {}).get("matches") or []
    for m in matches:
        if not isinstance(m, dict):
            continue
        ch = m.get("channel") or {}
        ch_name = ch.get("name") if isinstance(ch, dict) else ""
        ch_id = ch.get("id") if isinstance(ch, dict) else ""
        label = f"#{ch_name}" if ch_name else (f"channel:{ch_id}" if ch_id else "Slack")
        user_label = (m.get("username") or m.get("user") or "").strip()
        text = (m.get("text") or "").replace("\n", " ").strip()[:240]
        out.append(
            {
                "kind": "slack_live",
                "title": label,
                "subtitle": user_label or "message",
                "snippet": text,
                "permalink": m.get("permalink") or "",
                "ts": m.get("ts"),
            }
        )
        if len(out) >= max_results:
            break
    return out


def _search_outlook_live_placeholder() -> list[dict[str, Any]]:
    """Microsoft Graph mail search is not implemented in core_app yet (no token store)."""
    return []


@user_search_bp.get("/api/search")
def user_search():
    """
    Search ingested messages, tasks, projects, project notes, and calendar titles.

    Query params:
      q — search string (min 2 chars after trim; multi-word = AND on tokens)
      user_id — optional; when it looks like an email, results are scoped to that mailbox/workspace
      limit — max hits per bucket (default 20, max 40)
      live — if ``0`` / ``false`` / ``no``, skip Gmail/Slack live API calls (default: on)
    """
    q = (request.args.get("q") or "").strip()
    user_id = (request.args.get("user_id") or "").strip().lower()
    should_scope_workspace = bool(user_id and "@" in user_id)
    live_raw = (request.args.get("live") or "1").strip().lower()
    want_live = live_raw not in ("0", "false", "no", "off")
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
                        "gmail_live": [],
                        "slack_live": [],
                        "outlook_live": [],
                        "tasks": [],
                        "projects": [],
                        "project_notes": [],
                        "calendar": [],
                    },
                }
            ),
            200,
        )

    gmail_q = _gmail_query_from_tokens(tokens)

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
        "gmail_live": [],
        "slack_live": [],
        "outlook_live": [],
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

    if want_live:
        live_limit = min(per_bucket, 20)
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_gmail = ex.submit(_search_gmail_live, gmail_q=gmail_q, max_results=live_limit)
            f_slack = ex.submit(_search_slack_live, query=q, max_results=live_limit)
            for fut in as_completed([f_gmail, f_slack]):
                try:
                    rows = fut.result()
                except Exception as e:
                    log.warning("[user_search] live worker failed: %s", e)
                    continue
                if not rows:
                    continue
                k = rows[0].get("kind")
                if k == "gmail_live":
                    hits["gmail_live"] = rows
                elif k == "slack_live":
                    hits["slack_live"] = rows
        hits["outlook_live"] = _search_outlook_live_placeholder()

    total = sum(len(v) for v in hits.values())
    log.info("[user_search] q=%r tokens=%s total=%s", q, tokens, total)
    return jsonify({"success": True, "q": q, "tokens": tokens, "hits": hits, "total": total}), 200


__all__ = ["user_search_bp"]
