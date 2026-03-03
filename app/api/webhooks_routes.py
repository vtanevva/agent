"""Webhook endpoints (e.g., Gmail Pub/Sub push)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.config import Config
from app.services.gmail_pubsub_service import enqueue_gmail_pubsub_notification
from app.utils.logging_utils import get_logger

logger = get_logger(__name__)

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")


def _is_valid_secret() -> bool:
    """
    Shared-secret verification for webhook callers.

    Note:
    - In production, you should prefer Pub/Sub push with OIDC and verify the JWT.
    - For MVP, we accept a static secret via header/query param.
    """
    expected = (Config.GMAIL_PUBSUB_WEBHOOK_SECRET or "").strip()
    if not expected:
        # Dev-friendly default: if no secret is configured, allow.
        # Keep a visible warning so production doesn't accidentally run open.
        if Config.is_production():
            return False
        logger.warning("Gmail Pub/Sub webhook secret is not configured; allowing request (dev mode).")
        return True

    provided = (request.headers.get("X-Webhook-Secret") or request.args.get("secret") or "").strip()
    return bool(provided) and provided == expected


@webhooks_bp.route("/gmail/pubsub", methods=["POST"])
def gmail_pubsub_push():
    """
    Pub/Sub push endpoint for Gmail watch notifications.

    Pub/Sub push body (envelope) looks like:
      {"message": {"data": "<base64>", "messageId": "...", ...}, "subscription": "..."}
    Where decoded `data` is JSON:
      {"emailAddress": "user@gmail.com", "historyId": "123456"}
    """
    if not _is_valid_secret():
        return jsonify({"success": False, "error": "unauthorized"}), 401

    envelope = request.get_json(force=True, silent=True) or {}
    try:
        job_id = enqueue_gmail_pubsub_notification(envelope)
        # Pub/Sub expects a 2xx quickly; processing happens async.
        return jsonify({"success": True, "job_id": job_id}), 202
    except Exception as e:
        logger.error(f"Failed to enqueue Gmail Pub/Sub notification: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

