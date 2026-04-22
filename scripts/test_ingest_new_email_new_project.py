#!/usr/bin/env python3
"""
Exercise Gmail ingest with a brand-new client + explicit new project name.

Calls POST {CORE_BACKEND_URL}/ingest/gmail (default http://127.0.0.1:5000).
Expects ``explicit_project_name`` resolution → ``create_project`` when the name
does not yet exist for that client.

Usage (core server running):
  python scripts/test_ingest_new_email_new_project.py

Offline (no HTTP; runs ``process_normalized_message`` in-process from repo layout):
  python scripts/test_ingest_new_email_new_project.py --offline

Optional:
  set CORE_BACKEND_URL, or GRAFIK_LIST_ID if you want the Grafik branch past ``ignored``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _run_offline() -> int:
    """Same resolution path as /ingest/gmail without Flask (needs repo + backend on sys.path)."""
    repo = Path(__file__).resolve().parents[1]
    backend = repo / "backend"
    sys.path.insert(0, str(backend))
    sys.path.insert(0, str(repo))

    from application.orchestrators.event_orchestrator import handle_normalized_event
    from services.gmail_text import build_gmail_source_id, clean_email_text, prepare_email_for_classification

    mid = f"offline-{uuid.uuid4().hex[:14]}"
    client = f"OfflineClient-{uuid.uuid4().hex[:6]}"
    project = f"OfflineProject-{uuid.uuid4().hex[:6]}"
    subject = f"Kickoff: {project}"
    body = f"We start {project} for {client} next week. Confirm timeline."
    clean = clean_email_text(subject, body)
    tfc = prepare_email_for_classification(subject, body)
    sid = build_gmail_source_id(mid, f"t-{mid}", "pm@example.com", subject)
    normalized = {
        "source": "gmail",
        "workspace_id": "offline-test",
        "source_id": sid,
        "channel": "pm@example.com",
        "thread_id": f"t-{mid}",
        "ts": "2026-04-23T12:00:00Z",
        "sender": "pm@example.com",
        "user_id": None,
        "recipient": "you@company.com",
        "subject": subject,
        "raw_text": clean,
        "text_for_classification": tfc,
        "payload": {"client_name": client, "project_name": project},
        "client_name_hint": client,
        "project_name_hint": project,
        "grafik_list_id_hint": (os.environ.get("GRAFIK_LIST_ID") or "").strip() or None,
        "project_resolution_reason": "explicit_project_name",
        "project_confidence": 1.0,
        "needs_project_review": False,
    }
    out = handle_normalized_event(normalized)
    pick = {
        "status": out.get("status"),
        "reason": out.get("reason"),
        "client_id": out.get("client_id"),
        "project_id": out.get("project_id"),
        "client_name": out.get("client_name"),
        "project_name": out.get("project_name"),
        "project_resolution_reason": out.get("project_resolution_reason"),
        "has_action": (out.get("classification") or {}).get("has_action"),
    }
    print(json.dumps(pick, indent=2))
    return 0


def main() -> int:
    base = (os.environ.get("CORE_BACKEND_URL") or "http://127.0.0.1:5000").rstrip("/")
    mid = f"test-msg-{uuid.uuid4().hex[:16]}"
    client = f"AivisTestClient-{uuid.uuid4().hex[:6]}"
    project = f"NeptuneMigration-{uuid.uuid4().hex[:6]}"

    body: dict = {
        "source": "gmail",
        "workspace_id": "local-test",
        "message_id": mid,
        "thread_id": f"thread-{mid}",
        "from": "pm@example.com",
        "to": "you@company.com",
        "subject": f"Kickoff: {project}",
        "text": (
            f"Hi — we are kicking off {project} for {client} next week.\n"
            "Please confirm scope, owners, and timeline.\n"
            "Thanks."
        ),
        "timestamp": "2026-04-23T12:00:00Z",
        "client_name": client,
        "project_name": project,
    }
    gid = (os.environ.get("GRAFIK_LIST_ID") or "").strip()
    if gid:
        body["grafik_list_id"] = gid

    url = f"{base}/ingest/gmail"
    raw = json.dumps(body).encode("utf-8")
    req = Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode())
    except HTTPError as e:
        print(f"HTTP {e.code} from {url}")
        print(e.read().decode()[:4000])
        return 1
    except URLError as e:
        print(f"Could not reach {url}: {e}")
        print("Start the core API: python server.py core")
        return 1

    pick = {
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "client_id": payload.get("client_id"),
        "project_id": payload.get("project_id"),
        "client_name": payload.get("client_name"),
        "project_name": payload.get("project_name"),
        "project_resolution_reason": payload.get("project_resolution_reason"),
        "project_confidence": payload.get("project_confidence"),
        "needs_project_review": payload.get("needs_project_review"),
        "has_action": (payload.get("classification") or {}).get("has_action"),
        "list_id": payload.get("list_id"),
        "grafik_task_id": payload.get("grafik_task_id"),
    }
    print(json.dumps(pick, indent=2))
    print("\nFull response keys:", sorted(payload.keys()))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--offline",
        action="store_true",
        help="Run ingest in-process (no core HTTP server).",
    )
    args = ap.parse_args()
    raise SystemExit(_run_offline() if args.offline else main())
