"""
AI chat HTTP service (orchestrator + agents).

Run from repo root: ``python server.py ai``  (recommended), or ``python backend/ai_app.py``.
Gunicorn (see start-ai.sh, cwd=repo root): ``gunicorn backend.ai_app:app``
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
# Match ``core_app.py``: repo root first for ``integrations.grafik``; backend dir for ``application.*``.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

for _env_path in (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"):
    load_dotenv(_env_path)

from flask import Flask, jsonify, request
from flask_cors import CORS

from backend.application.orchestrators.ai_chat_orchestrator import get_orchestrator
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def create_app() -> Flask:
    flask_app = Flask(__name__)
    CORS(flask_app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
    expected_secret = (os.getenv("AI_SERVICE_SECRET") or "").strip()

    @flask_app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "ai_chat"}), 200

    @flask_app.post("/v1/chat")
    def v1_chat():
        if expected_secret:
            got = (request.headers.get("X-AI-Service-Secret") or "").strip()
            if got != expected_secret:
                return jsonify({"success": False, "error": "unauthorized"}), 401

        body = request.get_json(silent=True) or {}
        user_id = (str(body.get("user_id") or body.get("userId") or "")).strip()
        session_id = (str(body.get("session_id") or body.get("sessionId") or "")).strip()
        user_message = body.get("message") or body.get("text") or body.get("user_message") or ""
        user_message = str(user_message or "")
        message_type = body.get("message_type") or body.get("messageType")
        metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else None

        if not user_id or not session_id:
            return jsonify({"success": False, "error": "missing_user_id_or_session_id"}), 400

        try:
            orchestrator = get_orchestrator()
            intent, reply = orchestrator.handle_chat(
                user_id=user_id,
                session_id=session_id,
                user_message=user_message,
                metadata=metadata,
                message_type=message_type,
            )
        except Exception as e:
            logger.exception("Orchestrator error: %s", e)
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "orchestrator_error",
                        "intent": "general",
                        "reply": "I'm having trouble processing that right now. Please try again.",
                    }
                ),
                500,
            )

        return jsonify({"success": True, "intent": intent, "reply": reply}), 200

    return flask_app


# WSGI: ``gunicorn backend.ai_app:app`` (cwd = repo root)
app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("AI_CHAT_PORT", "5055"))
    logger.info("Starting AI chat service on :%s", port)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
