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

from routes.slack import slack_bp
from routes.slack_interactive import slack_interactive_bp
from routes.gmail import gmail_bp
from routes.webhooks import webhooks_bp
from routes.debug import debug_bp
from routes.classification_debug import classify_bp
from routes.debug_sql import sql_debug_bp
from routes.context import context_bp
from routes.metrics import metrics_bp
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
        return resp

    return app


app = create_app()

if __name__ == "__main__":
    log.info(f"Starting backend Flask on :5000 pid={os.getpid()} exe={sys.executable}")
    app.run(port=5000, debug=False)