"""
Gmail Pub/Sub watch processing (push → history delta → ingest).

Flow:
1) Pub/Sub pushes an envelope with base64 `message.data`
2) Decode to {emailAddress, historyId}
3) Use Gmail History API to list message/thread changes since last_history_id
4) Ingest changed threads into Mongo `emails` and enqueue workers (facts/relationships/tasks/linking)
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Set, Tuple

from googleapiclient.errors import HttpError

from app.db.collections import get_gmail_watch_state_collection
from app.memory.background_jobs import get_job_queue
from app.services.email_processing_pipeline import enqueue_thread_email_pipeline
from app.services.cache_service import cache_clear_pattern
from app.utils.google_api_helpers import get_gmail_service
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class GmailPushNotification:
    email_address: str
    history_id: int
    pubsub_message_id: Optional[str] = None


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def _coerce_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(str(v))
    except Exception:
        return None


def _decode_pubsub_envelope(envelope: Dict[str, Any]) -> GmailPushNotification:
    """
    Decode Pub/Sub push payload to a Gmail watch notification.
    """
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


def enqueue_gmail_pubsub_notification(envelope: Dict[str, Any]) -> str:
    """
    Enqueue processing for a Pub/Sub push notification.
    Returns a job_id.
    """
    notif = _decode_pubsub_envelope(envelope)
    job_queue = get_job_queue()

    # Deterministic-ish job id to reduce duplicate work on Pub/Sub retries
    safe_email = notif.email_address.replace("@", "_at_").replace(".", "_")
    job_id = f"gmail-pubsub-{safe_email}-{notif.history_id}"

    def _job():
        process_gmail_history_delta(notif)

    return job_queue.enqueue(_job, job_id=job_id)


def _get_last_history_id(email_address: str) -> Optional[int]:
    col = get_gmail_watch_state_collection()
    if col is None:
        return None
    doc = col.find_one({"_id": email_address}, {"last_history_id": 1})
    return _coerce_int(doc.get("last_history_id")) if doc else None


def _get_app_user_id(email_address: str) -> Optional[str]:
    col = get_gmail_watch_state_collection()
    if col is None:
        return None
    doc = col.find_one({"_id": email_address}, {"app_user_id": 1})
    v = (doc or {}).get("app_user_id")
    return str(v).strip() if v else None


def _set_last_history_id(email_address: str, history_id: int, *, note: str = "") -> None:
    col = get_gmail_watch_state_collection()
    if col is None:
        return
    update = {
        "$set": {
            "_id": email_address,
            "email_address": email_address,
            "last_history_id": int(history_id),
            "updated_at": _utcnow_iso(),
        }
    }
    if note:
        update["$set"]["note"] = note
    col.update_one({"_id": email_address}, update, upsert=True)


def _iter_history_message_additions(
    service,
    *,
    start_history_id: int,
) -> Tuple[Set[str], Optional[int]]:
    """
    Returns (thread_ids, latest_history_id_seen).
    """
    thread_ids: Set[str] = set()
    latest_history_id: Optional[int] = None

    page_token = None
    while True:
        req = service.users().history().list(
            userId="me",
            startHistoryId=str(start_history_id),
            historyTypes=["messageAdded"],
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
                tid = msg.get("threadId")
                if tid:
                    thread_ids.add(str(tid))

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return thread_ids, latest_history_id


def process_gmail_history_delta(notif: GmailPushNotification) -> None:
    """
    Worker: use historyId delta to find new threads and ingest them.
    """
    email_address = notif.email_address
    app_user_id = _get_app_user_id(email_address) or email_address
    last_history_id = _get_last_history_id(email_address)

    # If we have no baseline, store the historyId and wait for the next push.
    # (Gmail History API requires a valid startHistoryId baseline.)
    if last_history_id is None:
        _set_last_history_id(email_address, notif.history_id, note="baseline_from_first_push")
        logger.info(f"[GMAIL PUSH] Baseline historyId set for {email_address}: {notif.history_id}")
        return

    # If Pub/Sub delivers an older/duplicate notification, ignore.
    if notif.history_id <= last_history_id:
        logger.info(
            f"[GMAIL PUSH] Ignoring duplicate/old notification for {email_address}: "
            f"historyId={notif.history_id} <= last={last_history_id}"
        )
        return

    try:
        # Prefer app_user_id for credential lookup; fallback to email_address.
        try:
            service = get_gmail_service(app_user_id)
        except Exception:
            service = get_gmail_service(email_address)
    except Exception as e:
        logger.error(f"[GMAIL PUSH] Gmail service unavailable for {email_address}: {e}")
        return

    try:
        thread_ids, latest_seen = _iter_history_message_additions(service, start_history_id=last_history_id)
    except HttpError as e:
        # Common: 404 if startHistoryId is too old or invalid; recover by resetting baseline
        status = getattr(getattr(e, "resp", None), "status", None)
        if status == 404:
            logger.warning(
                f"[GMAIL PUSH] History delta invalid/too old for {email_address} (start={last_history_id}). "
                "Resetting baseline and waiting for future pushes (no backfill)."
            )
            _set_last_history_id(email_address, notif.history_id, note="history_too_old_reset_no_backfill")
            return
        logger.error(f"[GMAIL PUSH] History API error for {email_address}: {e}", exc_info=True)
        return
    except Exception as e:
        logger.error(f"[GMAIL PUSH] Failed to list history for {email_address}: {e}", exc_info=True)
        return

    # Update baseline to the latest id we saw (or the pushed id)
    new_baseline = int(latest_seen or notif.history_id)
    _set_last_history_id(email_address, new_baseline, note="processed")

    if not thread_ids:
        logger.info(f"[GMAIL PUSH] No new threads for {email_address} (historyId {notif.history_id})")
        return

    # Ingest just the changed threads and run workers
    try:
        job_id = enqueue_thread_email_pipeline(user_id=app_user_id, thread_ids=sorted(thread_ids), provider="gmail")
        logger.info(f"[GMAIL PUSH] Enqueued ingest for {email_address}: {len(thread_ids)} thread(s) (job={job_id})")
        # Invalidate cached email lists so the next "list emails" reflects the new inbox state.
        try:
            cache_clear_pattern(f"email_list:*{app_user_id}*")
            if app_user_id != email_address:
                cache_clear_pattern(f"email_list:*{email_address}*")
        except Exception:
            pass
    except Exception as e:
        logger.error(f"[GMAIL PUSH] Failed to enqueue ingest for {email_address}: {e}", exc_info=True)

