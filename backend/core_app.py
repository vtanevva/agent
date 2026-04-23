from __future__ import annotations

import os
import sys
from pathlib import Path

# Core SQLite + webhooks Flask API.
# Run from repo root: `python server.py core`  (recommended), or `cd backend && python core_app.py`.
# Gunicorn (see start.sh, cwd=backend): `gunicorn core_app:app`
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
# Repo root first for assets and ``from backend.*`` when cwd is backend; ``integrations.grafik`` lives in
# ``backend/integrations/grafik`` so it resolves whether ``sys.path[0]`` is repo root or backend (Gunicorn).
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, abort, jsonify, make_response, request, send_from_directory

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
from api.routes.google_oauth import google_oauth_bp
from api.routes.google_calendar import google_calendar_bp
from api.routes.recent_messages import recent_messages_bp
from storage.sqlite_db import init_sqlite
from utils.logger import get_logger


log = get_logger("backend")


def create_app():
    _backend_dir = Path(__file__).resolve().parent
    flask_app = Flask(
        __name__,
        static_folder=str(_backend_dir / "static"),
        static_url_path="/static",
    )
    # Required for /google/auth → Google → /google/oauth2callback (OAuth state in session).
    flask_app.secret_key = (os.getenv("FLASK_SECRET_KEY") or "dev-only-change-FLASK_SECRET_KEY").strip()
    init_sqlite()

    _waitlist_dir = _backend_dir / "static" / "waitlist"
    _web_build_dir = REPO_ROOT / "web-build"

    @flask_app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @flask_app.get("/")
    def root():
        """
        OAuth used to redirect here when expo_redirect was ``/`` (same host as API) → confusing 404.
        If ``web-build`` exists (Expo export, see repo Dockerfile), serve the web app; otherwise a tiny API landing page.
        """
        if request.args.get("gmail_oauth") == "1":
            user = (request.args.get("oauth_username") or "").strip()
            html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Google connected</title></head>
<body style="font-family:system-ui,sans-serif;max-width:36rem;margin:3rem auto;padding:0 1rem">
  <h1>Google account linked</h1>
  <p>Token saved for this server. You can close this tab and return to the app.</p>
  {f"<p><small>Username: {user}</small></p>" if user else ""}
  <p><a href="/health">API health</a></p>
</body></html>"""
        elif request.args.get("gmail_oauth_error"):
            err = (request.args.get("gmail_oauth_error") or "unknown").strip()
            html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Google sign-in</title></head>
<body style="font-family:system-ui,sans-serif;max-width:36rem;margin:3rem auto;padding:0 1rem">
  <h1>Google sign-in did not finish</h1>
  <p><code>{err}</code></p>
  <p>Try again from the app, or set <code>OAUTH_FRONTEND_RETURN_URL</code> to your Expo web URL.</p>
</body></html>"""
        else:
            if _web_build_dir.is_dir() and (_web_build_dir / "index.html").is_file():
                return send_from_directory(_web_build_dir, "index.html")
            html = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Mental core API</title></head>
<body style="font-family:system-ui,sans-serif;max-width:36rem;margin:3rem auto;padding:0 1rem">
  <h1>Mental core API</h1>
  <p>This origin serves Gmail OAuth, webhooks, and SQLite-backed routes. Open the Expo app for the UI.</p>
  <p><a href="/health">GET /health</a></p>
</body></html>"""
        r = make_response(html)
        r.headers["Content-Type"] = "text/html; charset=utf-8"
        return r

    @flask_app.get("/waitlist-admin")
    @flask_app.get("/waitlist-admin/")
    def waitlist_admin_login():
        """Static waitlist admin login (expects /api/waitlist/* when those routes exist)."""
        return send_from_directory(_waitlist_dir, "admin_login.html")

    @flask_app.get("/waitlist-admin/dashboard")
    def waitlist_admin_dashboard():
        return send_from_directory(_waitlist_dir, "admin.html")

    flask_app.register_blueprint(slack_bp)
    flask_app.register_blueprint(slack_interactive_bp)
    flask_app.register_blueprint(gmail_bp)
    flask_app.register_blueprint(gmail_watch_bp)
    flask_app.register_blueprint(action_items_bp)
    flask_app.register_blueprint(chat_api_bp)
    flask_app.register_blueprint(gmail_reply_bp)
    flask_app.register_blueprint(webhooks_bp)
    flask_app.register_blueprint(debug_bp)
    flask_app.register_blueprint(classify_bp)
    flask_app.register_blueprint(sql_debug_bp)
    flask_app.register_blueprint(context_bp)
    flask_app.register_blueprint(metrics_bp)
    flask_app.register_blueprint(google_oauth_bp)
    flask_app.register_blueprint(google_calendar_bp)
    flask_app.register_blueprint(recent_messages_bp)

    @flask_app.get("/<path:spa_path>")
    def spa_or_asset(spa_path: str):
        """
        Serve Expo web static export and SPA deep links. Registered after blueprints so API routes win.
        """
        if not _web_build_dir.is_dir() or not (_web_build_dir / "index.html").is_file():
            abort(404)
        target = _web_build_dir / spa_path
        try:
            target.resolve().relative_to(_web_build_dir.resolve())
        except ValueError:
            abort(404)
        if target.is_file():
            return send_from_directory(_web_build_dir, spa_path)
        return send_from_directory(_web_build_dir, "index.html")

    @flask_app.before_request
    def _cors_preflight():
        if request.method == "OPTIONS":
            r = make_response("", 204)
            r.headers["Access-Control-Allow-Origin"] = "*"
            r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Webhook-Secret"
            r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            return r

    @flask_app.before_request
    def _log_request():
        log.info(f"[HTTP] {request.method} {request.path}")

    @flask_app.after_request
    def _log_response(resp):
        log.info(f"[HTTP] {request.method} {request.path} -> {resp.status_code}")
        # Allow Expo web (different port) to call this local backend.
        resp.headers.setdefault("Access-Control-Allow-Origin", "*")
        resp.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Webhook-Secret")
        resp.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        return resp

    return flask_app


# WSGI entry for gunicorn (cwd must be backend/): `gunicorn core_app:app`
app = create_app()

if __name__ == "__main__":
    log.info(f"Starting backend Flask on :5000 pid={os.getpid()} exe={sys.executable}")
    # Bind to 0.0.0.0 so Expo devices/emulators can reach it via LAN IP.
    app.run(host="0.0.0.0", port=5000, debug=False)
