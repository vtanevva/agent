"""
Gmail watch management (start/stop) + baseline persistence.

Gmail watch pushes notifications to Pub/Sub containing:
  - emailAddress
  - historyId

To process deltas reliably, we store a per-account baseline `last_history_id`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError

from app.config import Config
from app.db.collections import get_gmail_watch_state_collection
from app.utils.google_api_helpers import get_gmail_service
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def start_gmail_watch(
    *,
    user_id: str,
    email_address: str,
    topic_name: Optional[str] = None,
    label_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Start a Gmail watch for a user and persist baseline `historyId`.

    Parameters
    ----------
    user_id : str
        App user id (used for OAuth credential lookup and downstream ingestion keys).
    email_address : str
        Gmail address (must match what Gmail sends in push notifications).
        This is the primary key for watch state.
    topic_name : str, optional
        Pub/Sub topic resource name. Defaults to Config.GMAIL_PUBSUB_TOPIC.
    label_ids : list[str], optional
        Which labels to include. Defaults to ["INBOX"].
    """
    email_address = (email_address or "").strip().lower()
    if not email_address:
        return {"success": False, "error": "Missing email_address"}

    topic = (topic_name or Config.GMAIL_PUBSUB_TOPIC or "").strip()
    if not topic:
        return {"success": False, "error": "GMAIL_PUBSUB_TOPIC not configured"}

    label_ids = label_ids or ["INBOX"]

    try:
        svc = get_gmail_service(user_id)
        resp = (
            svc.users()
            .watch(
                userId="me",
                body={
                    "topicName": topic,
                    "labelIds": label_ids,
                    "labelFilterAction": "include",
                },
            )
            .execute()
        )
    except HttpError as e:
        return {"success": False, "error": f"Gmail watch error: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    history_id = resp.get("historyId")
    expiration = resp.get("expiration")  # ms since epoch (string)

    # Persist baseline under the Gmail address key (env-scoped collection)
    col = get_gmail_watch_state_collection()
    if col is not None:
        col.update_one(
            {"_id": email_address},
            {
                "$set": {
                    "_id": email_address,
                    "email_address": email_address,
                    "app_user_id": user_id,
                    "topic": topic,
                    "label_ids": label_ids,
                    "last_history_id": int(history_id) if history_id is not None else None,
                    "watch_expiration": expiration,
                    "watch_started_at": _utcnow_iso(),
                    "updated_at": _utcnow_iso(),
                }
            },
            upsert=True,
        )

    logger.info(f"✅ Gmail watch started for {email_address} (app_user_id={user_id}) historyId={history_id}")
    return {"success": True, "email_address": email_address, "historyId": history_id, "expiration": expiration, "topic": topic}


def stop_gmail_watch(*, user_id: str) -> Dict[str, Any]:
    """Stop Gmail watch notifications for the authenticated user."""
    try:
        svc = get_gmail_service(user_id)
        svc.users().stop(userId="me").execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

