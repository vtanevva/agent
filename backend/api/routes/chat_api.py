from __future__ import annotations

import io
import os
from typing import Any

from flask import Blueprint, jsonify, request

from application.orchestrators.chat_orchestrator import handle_chat_turn
from application.services.thread_service import (
    list_chat_sessions,
    load_chat_session_messages,
)
from utils.logger import get_logger


log = get_logger("chat_api")
chat_api_bp = Blueprint("chat_api", __name__)


def _safe_str(v: Any) -> str:
    return (str(v) if v is not None else "").strip()


@chat_api_bp.post("/api/chat")
def api_chat():
    """
    Unified chat endpoint:
    - generates reply via AI chat service (HTTP: AI_SERVICE_URL, default :5055)
    - persists conversation into SQLite (/backend) as source='chat'
    """
    payload = request.get_json(silent=True) or {}
    user_id = _safe_str(payload.get("user_id") or payload.get("userId"))
    session_id = _safe_str(payload.get("session_id") or payload.get("sessionId"))
    user_message = payload.get("message") or payload.get("text") or payload.get("user_message") or ""
    user_message = str(user_message or "")

    message_type = payload.get("message_type") or payload.get("messageType")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
    reply_draft = payload.get("reply_draft") if isinstance(payload.get("reply_draft"), dict) else None
    if reply_draft:
        metadata = dict(metadata or {})
        metadata["reply_draft"] = reply_draft
    draft_polish = payload.get("draft_polish") if isinstance(payload.get("draft_polish"), dict) else None
    if draft_polish:
        metadata = dict(metadata or {})
        metadata["draft_polish"] = draft_polish

    if not user_id or not session_id:
        return jsonify({"success": False, "error": "missing_user_id_or_session_id"}), 400

    result = handle_chat_turn(
        user_id=user_id,
        session_id=session_id,
        user_message=user_message,
        message_type=message_type,
        metadata=metadata,
    )
    return jsonify({"success": True, "intent": result["intent"], "reply": result["reply"]}), 200


@chat_api_bp.post("/api/session_chat")
def session_chat():
    payload = request.get_json(silent=True) or {}
    user_id = _safe_str(payload.get("user_id") or payload.get("userId"))
    session_id = _safe_str(payload.get("session_id") or payload.get("sessionId"))
    if not user_id or not session_id:
        return jsonify({"chat": []}), 200

    return jsonify({"chat": load_chat_session_messages(user_id=user_id, session_id=session_id)}), 200


@chat_api_bp.post("/api/sessions-log")
def sessions_log():
    payload = request.get_json(silent=True) or {}
    user_id = _safe_str(payload.get("user_id") or payload.get("userId"))
    if not user_id:
        return jsonify({"sessions": []}), 200

    return jsonify({"sessions": list_chat_sessions(user_id=user_id)}), 200


@chat_api_bp.post("/api/transcribe")
def api_transcribe():
    """
    Voice-to-text via OpenAI Whisper. Accepts multipart uploads (``file``/``audio``)
    from expo-av on mobile and web fallbacks. Used by the VoiceChat page so mobile
    users (where there is no Web Speech API) can speak into the same chat entry
    point as the keyboard chat (``/api/chat``).
    """
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return jsonify({"success": False, "error": "transcription_unavailable"}), 503

    upload = None
    for key in ("file", "audio", "recording"):
        if key in request.files:
            upload = request.files[key]
            break

    if upload is None and request.data:
        filename = (request.headers.get("X-Audio-Filename") or "audio.m4a").strip()
        upload = io.BytesIO(request.data)
        upload.name = filename  # type: ignore[attr-defined]

    if upload is None:
        return jsonify({"success": False, "error": "missing_audio"}), 400

    language = (request.form.get("language") or request.args.get("language") or "").strip() or None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        stream = upload.stream if hasattr(upload, "stream") else upload
        filename = getattr(upload, "filename", None) or getattr(upload, "name", "audio.m4a")

        # openai>=1.x expects a tuple (filename, fileobj, content_type) OR a file-like with .name
        payload = stream.read()
        fileobj = io.BytesIO(payload)
        fileobj.name = filename
        kwargs: dict[str, Any] = {"model": "whisper-1", "file": fileobj}
        if language:
            kwargs["language"] = language

        result = client.audio.transcriptions.create(**kwargs)
        text = getattr(result, "text", None) or (result.get("text") if isinstance(result, dict) else "")
        text = (text or "").strip()
    except Exception as e:  # noqa: BLE001 - surfaced to client
        log.exception("transcribe failed: %s", e)
        return jsonify({"success": False, "error": "transcribe_failed"}), 500

    return jsonify({"success": True, "text": text}), 200


__all__ = ["chat_api_bp"]

