from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse

from flask import Blueprint, jsonify, request

from services.gmail_pubsub import decode_pubsub_envelope, process_gmail_history_delta
from utils.logger import get_logger


log = get_logger("webhooks")
webhooks_bp = Blueprint("webhooks", __name__)

def _normalize_configured_secret(raw: str | None) -> str:
    """
    Accept either a plain token (expected) or an accidental full URL that
    contains `?secret=...` and extract the token.
    """
    v = (raw or "").strip()
    if not v:
        return ""

    # Common misconfig: env var set to the full webhook URL.
    if v.startswith("http://") or v.startswith("https://"):
        try:
            qs = parse_qs(urlparse(v).query)
            extracted = (qs.get("secret") or [None])[0]
            extracted = (extracted or "").strip()
            if extracted:
                return extracted
        except Exception:
            pass

    # Fallback: best-effort extract if raw contains `secret=` but isn't a URL.
    if "secret=" in v:
        try:
            tail = v.split("secret=", 1)[1]
            extracted = tail.split("&", 1)[0].strip()
            if extracted:
                return extracted
        except Exception:
            pass

    return v


@webhooks_bp.post("/webhooks/gmail/pubsub")
@webhooks_bp.post("/api/webhooks/gmail/pubsub")
def webhooks_gmail_pubsub():
    configured_secret = _normalize_configured_secret(os.getenv("GMAIL_PUBSUB_WEBHOOK_SECRET"))
    if configured_secret:
        provided_secret = (
            (request.headers.get("X-Webhook-Secret") or "").strip()
            or (request.args.get("secret") or "").strip()
        )
        if not provided_secret or provided_secret != configured_secret:
            log.info(
                "[WEBHOOKS] pubsub unauthorized ip=%s has_header=%s has_query=%s",
                (request.remote_addr or ""),
                bool(request.headers.get("X-Webhook-Secret")),
                bool(request.args.get("secret")),
            )
            return jsonify({"success": False, "error": "unauthorized"}), 401

    envelope = request.get_json(silent=True) or {}
    msg = envelope.get("message") if isinstance(envelope, dict) else None
    message_id = None
    if isinstance(msg, dict):
        message_id = msg.get("messageId") or msg.get("message_id")

    log.info(
        "[WEBHOOKS] pubsub received message_id=%s",
        str(message_id) if message_id is not None else None,
    )

    try:
        notif = decode_pubsub_envelope(envelope)
    except Exception as err:
        log.info(f"[WEBHOOKS] invalid pubsub envelope: {err}")
        return jsonify({"success": False, "error": str(err)}), 400

    result = process_gmail_history_delta(notif)
    http_status = 200 if result.get("success") else 500
    log.info(
        "[WEBHOOKS] pubsub processed email=%s history_id=%s status=%s success=%s http=%s",
        (result.get("email_address") or getattr(notif, "email_address", None)),
        (result.get("history_id") or getattr(notif, "history_id", None)),
        result.get("status"),
        bool(result.get("success")),
        http_status,
    )
    return jsonify(result), http_status


__all__ = ["webhooks_bp"]

