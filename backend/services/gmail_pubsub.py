from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Tuple

from googleapiclient.errors import HttpError

from services.gmail_auth import get_gmail_service
from services.gmail_draft import create_gmail_draft
from services.gmail_message import extract_plain_text, get_header
from services.unified_processor import process_normalized_message
from services.gmail_text import clean_email_text, prepare_email_for_classification, build_gmail_source_id
from utils.logger import get_logger
from storage.sqlite_db import (
    get_gmail_watch_state,
    get_gmail_last_history_id,
    log_event,
    set_gmail_last_history_id,
    upsert_gmail_watch_state,
)

log = get_logger("gmail_pubsub")


@dataclass(frozen=True)
class GmailPushNotification:
    email_address: str
    history_id: int
    pubsub_message_id: Optional[str] = None


def _coerce_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(str(v))
    except Exception:
        return None


def decode_pubsub_envelope(envelope: Dict[str, Any]) -> GmailPushNotification:
    msg = envelope.get("message") or {}
    data_b64 = msg.get("data")
    if not data_b64:
        raise ValueError("Missing Pub/Sub message.data")

    try:
        raw = base64.b64decode(data_b64).decode("utf-8", errors="replace")
    except Exception as e:
        raise ValueError(f"Invalid base64 message.data: {e}")

    try:
        decoded = json.loads(raw)
    except Exception as e:
        raise ValueError(f"Invalid decoded Gmail notification JSON: {e}")

    email_address = str(decoded.get("emailAddress") or "").strip().lower()
    history_id = _coerce_int(decoded.get("historyId"))
    if not email_address or history_id is None:
        raise ValueError("Decoded notification missing emailAddress/historyId")

    pubsub_message_id = msg.get("messageId") or msg.get("message_id")
    return GmailPushNotification(
        email_address=email_address,
        history_id=history_id,
        pubsub_message_id=str(pubsub_message_id) if pubsub_message_id else None,
    )


def _safe_json_loads_list(v: Any) -> list[Any]:
    if not v:
        return []
    if isinstance(v, list):
        return v
    if not isinstance(v, str):
        return []
    try:
        obj = json.loads(v)
        return obj if isinstance(obj, list) else []
    except Exception:
        return []


def _get_watch_label_ids(email_address: str) -> list[str]:
    """
    Label IDs configured for this mailbox watch (stored in SQLite).
    When present, we only process messages that contain at least one of these labels.
    """
    state = get_gmail_watch_state(email_address)
    if not state:
        return []
    raw = state.get("label_ids_json")
    items = _safe_json_loads_list(raw)
    labels: list[str] = []
    for x in items:
        s = str(x or "").strip()
        if s:
            labels.append(s)
    return labels


def _iter_history_relevant_message_ids(
    service,
    *,
    start_history_id: int,
    watch_label_ids: list[str] | None = None,
) -> Tuple[Set[str], Optional[int]]:
    """
    Returns (message_ids, latest_history_id_seen).
    """
    message_ids: Set[str] = set()
    latest_history_id: Optional[int] = None

    # If we're configured to trigger on labeled emails (Zapier-style),
    # include labelAdded so we react when the label is applied after receipt.
    history_types = ["messageAdded"]
    if watch_label_ids:
        history_types = ["messageAdded", "labelAdded"]

    page_token = None
    while True:
        req = service.users().history().list(
            userId="me",
            startHistoryId=str(start_history_id),
            historyTypes=history_types,
            pageToken=page_token,
        )
        resp = req.execute()

        resp_history_id = _coerce_int(resp.get("historyId"))
        if resp_history_id is not None:
            latest_history_id = max(latest_history_id or resp_history_id, resp_history_id)

        history = resp.get("history") or []
        for h in history:
            for added in (h.get("messagesAdded") or []):
                msg = added.get("message") or {}
                mid = msg.get("id")
                if mid:
                    message_ids.add(str(mid))

            # When label triggers are configured, pick up messages when the
            # watched label is applied (even if not "new").
            if watch_label_ids:
                want = set(watch_label_ids)
                for la in (h.get("labelsAdded") or []):
                    mid = ((la.get("message") or {}).get("id") if isinstance(la, dict) else None)
                    if not mid:
                        continue
                    label_ids = la.get("labelIds") if isinstance(la, dict) else None
                    if isinstance(label_ids, list) and want.intersection({str(x) for x in label_ids if x}):
                        message_ids.add(str(mid))

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return message_ids, latest_history_id


def process_gmail_history_delta(notif: GmailPushNotification) -> Dict[str, Any]:
    """
    Core worker: use historyId delta to find new messages and ingest them through
    the existing backend Gmail ingestion pipeline.
    """
    email_address = notif.email_address
    last_history_id = get_gmail_last_history_id(email_address)
    watch_label_ids = _get_watch_label_ids(email_address)

    # If we have no baseline, store the pushed historyId and wait for the next push (no backfill).
    if last_history_id is None:
        set_gmail_last_history_id(email_address, notif.history_id, note="baseline_from_first_push")
        log.info(f"[GMAIL PUSH] Baseline historyId set for {email_address}: {notif.history_id}")
        return {"success": True, "status": "baseline_set", "email_address": email_address, "history_id": notif.history_id}

    # Pub/Sub is at-least-once; skip duplicates/out-of-order.
    if notif.history_id <= last_history_id:
        return {
            "success": True,
            "status": "skipped",
            "reason": "already_processed",
            "email_address": email_address,
            "history_id": notif.history_id,
            "last_history_id": last_history_id,
        }

    try:
        service = get_gmail_service()
    except Exception as e:
        log.exception(f"[GMAIL PUSH] Gmail service unavailable: {e}")
        return {"success": False, "status": "error", "error": str(e)}

    try:
        message_ids, latest_seen = _iter_history_relevant_message_ids(
            service,
            start_history_id=last_history_id,
            watch_label_ids=watch_label_ids,
        )
    except HttpError as e:
        status = getattr(getattr(e, "resp", None), "status", None)
        if status == 404:
            # History too old/invalid -> reset baseline, no backfill.
            set_gmail_last_history_id(email_address, notif.history_id, note="history_too_old_reset_no_backfill")
            return {
                "success": True,
                "status": "baseline_reset",
                "reason": "history_too_old",
                "email_address": email_address,
                "history_id": notif.history_id,
                "last_history_id": last_history_id,
            }
        log.exception(f"[GMAIL PUSH] History API error: {e}")
        return {"success": False, "status": "error", "error": str(e)}
    except Exception as e:
        log.exception(f"[GMAIL PUSH] Failed to list history: {e}")
        return {"success": False, "status": "error", "error": str(e)}

    new_baseline = int(latest_seen or notif.history_id)
    set_gmail_last_history_id(email_address, new_baseline, note="processed")

    if not message_ids:
        return {"success": True, "status": "no_changes", "email_address": email_address, "history_id": notif.history_id}

    ingested = 0
    failed = 0

    for mid in sorted(message_ids):
        try:
            msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
            thread_id = str(msg.get("threadId") or "")
            msg_label_ids = msg.get("labelIds") or []

            # Zapier-style: only trigger when the message has a watched label.
            if watch_label_ids:
                have = {str(x) for x in msg_label_ids if x}
                want = set(watch_label_ids)
                if not have.intersection(want):
                    continue

            payload = msg.get("payload") or {}
            headers = payload.get("headers") or []

            subject = get_header(headers, "Subject") or ""
            sender = get_header(headers, "From") or ""
            recipient = get_header(headers, "To") or ""
            body = extract_plain_text(payload) or ""

            # Reuse existing backend ingestion logic (same as /ingest/gmail route)
            clean_text_value = clean_email_text(subject, body)
            if not clean_text_value:
                continue

            source_id = build_gmail_source_id(mid, thread_id, sender, subject)
            text_for_classification = prepare_email_for_classification(subject, body)

            normalized = {
                "source": "gmail",
                "workspace_id": email_address,
                "source_id": source_id,
                "channel": sender,
                "thread_id": thread_id,
                "ts": str(msg.get("internalDate") or ""),
                "sender": sender,
                "user_id": None,
                "recipient": recipient,
                "subject": subject,
                "raw_text": clean_text_value,
                "text_for_classification": text_for_classification,
                "payload": {
                    "message_id": mid,
                    "thread_id": thread_id,
                    "from": sender,
                    "to": recipient,
                    "subject": subject,
                    "body": body,
                    "timestamp": msg.get("internalDate"),
                    "emailAddress": email_address,
                    # When the watch is configured with labels, treat matching messages as
                    # explicit triggers (Zapier-style): generate a draft immediately.
                    "force_draft_ready": bool(watch_label_ids),
                },
                "client_name_hint": "Email",
                "project_name_hint": "General",
                "grafik_list_id_hint": None,
                "channel_type": None,
                "project_resolution_reason": "fallback_general",
                "project_confidence": 0.3,
                "needs_project_review": False,
            }

            result = process_normalized_message(normalized) or {}

            # Create a real Gmail Draft immediately when allowed by policy.
            if result.get("should_create_draft") and result.get("reply_text"):
                try:
                    draft_subject = subject
                    if draft_subject and not draft_subject.lower().startswith("re:"):
                        draft_subject = f"Re: {draft_subject}"
                    elif not draft_subject:
                        draft_subject = "Re:"

                    draft_id = create_gmail_draft(
                        service=service,
                        to_email=sender,
                        subject=draft_subject,
                        reply_text=result.get("reply_text"),
                        thread_id=thread_id,
                        message_id=str(mid),
                    )

                    log.info(
                        f"[GMAIL_DRAFT:pubsub] email_address={email_address} "
                        f"message_id={mid} thread_id={thread_id} draft_id={draft_id}"
                    )
                    log_event(
                        source="gmail",
                        source_id=source_id,
                        step="gmail_draft_create",
                        status="ok",
                        data={
                            "workspace_id": email_address,
                            "draft_id": draft_id,
                            "thread_id": thread_id,
                            "message_id": str(mid),
                        },
                    )
                except Exception as e:
                    log.exception(
                        f"[GMAIL_DRAFT_ERROR:pubsub] email_address={email_address} "
                        f"message_id={mid} thread_id={thread_id} -> {e}"
                    )
                    log_event(
                        source="gmail",
                        source_id=source_id,
                        step="gmail_draft_create",
                        status="error",
                        data={
                            "workspace_id": email_address,
                            "thread_id": thread_id,
                            "message_id": str(mid),
                            "error": str(e),
                        },
                    )
            ingested += 1
        except Exception as e:
            failed += 1
            log.exception(f"[GMAIL PUSH] Ingest failed for message_id={mid}: {e}")

    return {
        "success": True,
        "status": "processed",
        "email_address": email_address,
        "history_id": notif.history_id,
        "last_history_id": new_baseline,
        "messages_seen": len(message_ids),
        "ingested": ingested,
        "failed": failed,
    }


def start_watch(*, email_address: str, topic: str, label_ids: list[str] | None = None) -> Dict[str, Any]:
    """
    Start Gmail watch (Pub/Sub) using the backend Gmail auth.
    Stores baseline historyId into SQLite.
    """
    topic = (topic or "").strip()
    if not topic:
        return {"success": False, "error": "Missing topic"}

    def _parse_env_labels() -> list[str]:
        raw = (os.getenv("GMAIL_WATCH_LABELS") or "").strip()
        if not raw:
            return []
        parts = [p.strip() for p in raw.split(",")]
        return [p for p in parts if p]

    def _resolve_label_ids(service, specs: list[str]) -> list[str]:
        """
        Accept label IDs (e.g. 'Label_123') or label names (e.g. 'Zapier').
        Returns label IDs.
        """
        specs = [str(s or "").strip() for s in (specs or []) if str(s or "").strip()]
        if not specs:
            return []

        resp = service.users().labels().list(userId="me").execute()
        labels = resp.get("labels") or []

        id_set = {str(l.get("id")) for l in labels if l.get("id")}
        name_to_id = {str(l.get("name") or "").strip().lower(): str(l.get("id")) for l in labels if l.get("id")}

        resolved: list[str] = []
        missing: list[str] = []
        for s in specs:
            if s in id_set:
                resolved.append(s)
                continue
            key = s.lower()
            if key in name_to_id:
                resolved.append(name_to_id[key])
                continue
            missing.append(s)

        if missing:
            raise RuntimeError(
                "Unknown Gmail label(s): "
                + ", ".join(missing)
                + ". Configure by label *name* or label *id*."
            )
        return resolved

    label_ids = label_ids or _parse_env_labels() or ["INBOX"]

    service = get_gmail_service()

    # Always resolve the actual Gmail address for the token account.
    # This prevents mismatches where the caller provides email_address for a different account.
    try:
        profile = service.users().getProfile(userId="me").execute()
        token_email = str((profile or {}).get("emailAddress") or "").strip().lower()
    except Exception as e:
        return {"success": False, "error": f"Failed to read Gmail profile for token account: {e}"}

    requested_email = (email_address or "").strip().lower()
    if requested_email and token_email and requested_email != token_email:
        return {
            "success": False,
            "error": "token_account_mismatch",
            "message": "backend/token.json is authorized for a different Gmail account than requested email_address",
            "requested_email_address": requested_email,
            "token_email_address": token_email,
        }

    # If caller omitted email_address, use the token account email.
    email_address = token_email or requested_email
    if not email_address:
        return {"success": False, "error": "Missing email_address (and could not resolve token account email)"}

    resolved_label_ids = _resolve_label_ids(service, label_ids)

    resp = (
        service.users()
        .watch(
            userId="me",
            body={
                "topicName": topic,
                "labelIds": resolved_label_ids,
                "labelFilterAction": "include",
            },
        )
        .execute()
    )

    history_id = _coerce_int(resp.get("historyId"))
    expiration = resp.get("expiration")

    upsert_gmail_watch_state(
        email_address=email_address,
        last_history_id=history_id,
        topic=topic,
        label_ids=resolved_label_ids,
        watch_expiration=str(expiration) if expiration is not None else None,
        note="watch_started",
    )

    return {"success": True, "email_address": email_address, "historyId": history_id, "expiration": expiration, "topic": topic, "label_ids": label_ids}


def stop_watch() -> Dict[str, Any]:
    service = get_gmail_service()
    service.users().stop(userId="me").execute()
    return {"success": True}

