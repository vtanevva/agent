from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running `python backend/app.py` from inside the backend venv/cwd.
# This keeps integrations as a separate layer at repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request

from api.routes.slack import slack_bp
from api.routes.slack_interactive import slack_interactive_bp
from api.routes.gmail import gmail_bp
from api.routes.gmail_watch import gmail_watch_bp
from api.routes.action_items import action_items_bp
from api.routes.chat_api import chat_api_bp
from api.routes.gmail_reply_routes import gmail_reply_bp
from api.routes.webhooks import webhooks_bp
from api.routes.debug import debug_bp
from api.routes.classification_debug import classify_bp
from api.routes.debug_sql import sql_debug_bp
from api.routes.context import context_bp
from api.routes.metrics import metrics_bp
from storage.sqlite_db import init_sqlite
from utils.logger import get_logger


log = get_logger("backend")


def create_app():
    app = Flask(__name__)
    init_sqlite()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    app.register_blueprint(slack_bp)
    app.register_blueprint(slack_interactive_bp)
    app.register_blueprint(gmail_bp)
    app.register_blueprint(gmail_watch_bp)
    app.register_blueprint(action_items_bp)
    app.register_blueprint(chat_api_bp)
    app.register_blueprint(gmail_reply_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(debug_bp)
    app.register_blueprint(classify_bp)
    app.register_blueprint(sql_debug_bp)
    app.register_blueprint(context_bp)
    app.register_blueprint(metrics_bp)

    @app.before_request
    def _log_request():
        log.info(f"[HTTP] {request.method} {request.path}")

    @app.after_request
    def _log_response(resp):
        log.info(f"[HTTP] {request.method} {request.path} -> {resp.status_code}")
        # Allow Expo web (different port) to call this local backend.
        resp.headers.setdefault("Access-Control-Allow-Origin", "*")
        resp.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Webhook-Secret")
        resp.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        return resp

    return app


app = create_app()

if __name__ == "__main__":
    log.info(f"Starting backend Flask on :5000 pid={os.getpid()} exe={sys.executable}")
    # Bind to 0.0.0.0 so Expo devices/emulators can reach it via LAN IP.
    app.run(host="0.0.0.0", port=5000, debug=False)