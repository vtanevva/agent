"""
Browser Gmail OAuth for the Expo / web app.

- GET  /google/auth/<username>     — starts OAuth (redirects to Google)
- GET  /google/oauth2callback      — Google redirects here; saves token; redirects to expo_redirect

Requires ``backend/credentials.json`` (Web or Desktop OAuth client). For a **Web** client, add this
exact redirect URI in Google Cloud Console → Credentials → Authorized redirect URIs::

    http://localhost:5000/google/oauth2callback
    http://127.0.0.1:5000/google/oauth2callback
    (and the same for your LAN IP / production host if used)

``FLASK_SECRET_KEY`` must be set in production so OAuth ``state`` survives in the session cookie.

Set ``OAUTH_FRONTEND_RETURN_URL`` to your Expo web origin (e.g. ``http://127.0.0.1:8081/``) so after
sign-in the browser returns to the app instead of ``GET /`` on the API host (which used to 404).

**Production ``redirect_uri_mismatch``:** Behind Railway/nginx, ``request.url_root`` is often wrong
(``http://`` or internal host). Set **one** of these to the exact callback Google must see (must also
be listed under Authorized redirect URIs for your Web client)::

    GOOGLE_OAUTH_REDIRECT_URI=https://YOUR_DOMAIN/google/oauth2callback
    # or full URL in GOOGLE_REDIRECT_URI / OAUTH_REDIRECT_URI
    # or only origin: PRODUCTION_URL / PUBLIC_API_URL=https://YOUR_DOMAIN  (path is appended)

Google Cloud Console must list that same URI character-for-character (scheme, host, path; no extra slash).

On **Railway + Gunicorn**, set ``FORWARDED_ALLOW_IPS=*`` (already the default in ``start.sh``) so the edge
proxy's ``X-Forwarded-Proto`` / ``Host`` reach Flask; otherwise ``request.url_root`` stays ``http://`` and
OAuth breaks even when env vars look correct.

Local **http** callbacks require oauthlib to allow non-TLS (this module sets it for ``localhost`` /
``127.0.0.1`` only). For **LAN IP** (e.g. ``192.168.x.x``) over http, set ``OAUTHLIB_INSECURE_TRANSPORT=1``
in your environment while testing — do not use that on a public deployment.
"""

from __future__ import annotations

import os
from urllib.parse import quote, urlencode, urlparse

from flask import Blueprint, abort, has_request_context, jsonify, redirect, request, session
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow

from services.gmail_auth import (
    SCOPES,
    get_client_secrets_path,
    load_google_credentials,
    save_google_credentials,
)
from utils.logger import get_logger

log = get_logger("google_oauth")

google_oauth_bp = Blueprint("google_oauth", __name__)

# ``Flow`` enables PKCE by default (``authorization_url`` sends ``code_challenge``). The callback
# builds a new ``Flow`` without the original ``code_verifier`` → Google ``invalid_grant`` / missing
# code verifier. This route uses a confidential Web client with ``client_secret``; PKCE is optional.
_FLOW_KWARGS = {"autogenerate_code_verifier": False}


def default_oauth_frontend_return_url() -> str:
    """
    Where the browser goes after Google redirects back to /google/oauth2callback.
    Must be an absolute URL to your Expo web (or hosted app), not the API origin — otherwise you get GET / on :5000 → 404.
    """
    u = (os.getenv("OAUTH_FRONTEND_RETURN_URL") or "http://127.0.0.1:8081/").strip()
    return u or "http://127.0.0.1:8081/"


def _stored_gmail_email() -> str | None:
    """Gmail address for the single stored ``token.json``, or ``None`` if missing/invalid."""
    creds: Credentials | None = load_google_credentials(None)
    if not creds:
        return None
    try:
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                save_google_credentials(None, creds)
    except Exception as e:
        log.warning("[OAuth] credential refresh: %s", e)
        return None
    if not creds.valid:
        return None
    try:
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress")
    except Exception as e:
        log.warning("[OAuth] Gmail profile read: %s", e)
        return None


def _callback_path() -> str:
    return "/google/oauth2callback"


def _parsed_hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_local_hostname(host: str) -> bool:
    h = (host or "").lower().split(":")[0]
    return not h or h in ("localhost", "127.0.0.1", "0.0.0.0") or h.endswith(".local")


def _request_public_hostname() -> str:
    """Hostname the client used (first hop), when not localhost."""
    if not has_request_context():
        return ""
    raw = (
        (request.headers.get("X-Forwarded-Host") or request.environ.get("HTTP_HOST") or request.host or "")
        .split(",")[0]
        .strip()
    )
    host = raw.split(":")[0].lower()
    return "" if _is_local_hostname(host) else host


def _oauth_redirect_uri_from_env() -> str | None:
    """
    Public OAuth callback URL, independent of ``request.url_root`` (broken behind reverse proxies).

    Checks env in priority order; values may be a full callback URL or an API origin only.
    """
    path = _callback_path()
    req_host = _request_public_hostname()

    def _finalize(raw: str) -> str:
        u = raw.split("?", 1)[0].strip().rstrip("/")
        if u.endswith(path):
            return u
        return f"{u}{path}"

    for key in ("GOOGLE_OAUTH_REDIRECT_URI", "GOOGLE_REDIRECT_URI", "OAUTH_REDIRECT_URI"):
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        candidate = _finalize(raw)
        # Copied .env often leaves localhost OAuth URIs in Railway — ignore them when the browser hit a public host.
        if req_host and _is_local_hostname(_parsed_hostname(candidate)):
            log.warning("[OAuth] skipping %s=... (localhost) because request Host is %s", key, req_host)
            continue
        return candidate

    for key in ("PUBLIC_API_URL", "PRODUCTION_URL", "RAILWAY_URL"):
        raw = (os.getenv(key) or "").strip()
        if not raw:
            continue
        if "://" not in raw:
            raw = f"https://{raw.lstrip('/')}"
        return _finalize(raw)

    return None


def _redirect_uri_from_public_host_header() -> str | None:
    """
    Build callback URL from Host / X-Forwarded-* when Gunicorn did not fix url_root yet.

    Google OAuth on the public internet requires https; Railway sets X-Forwarded-Proto when
    ``--forwarded-allow-ips`` is configured.
    """
    if not has_request_context():
        return None
    host = _request_public_hostname()
    if not host:
        return None
    proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    if proto == "https":
        scheme = "https"
    elif proto == "http":
        scheme = "http"
    else:
        # No forwarded proto (misconfigured proxy): assume TLS for real domains.
        scheme = "https"
    path = _callback_path()
    return f"{scheme}://{host}{path}"


def _redirect_uri() -> str:
    explicit = _oauth_redirect_uri_from_env()
    if explicit:
        return explicit
    from_host = _redirect_uri_from_public_host_header()
    if from_host:
        return from_host
    base = (request.url_root or "").rstrip("/")
    return f"{base}{_callback_path()}"


def _enable_oauthlib_http_for_local_callback() -> None:
    """
    oauthlib raises InsecureTransportError unless the callback URL is https.
    For local dev (http://localhost or http://127.0.0.1) this is expected; Google allows it.

    For phone/LAN testing over http, set ``OAUTHLIB_INSECURE_TRANSPORT=1`` in the environment
    (never in production on the public internet).
    """
    if (os.getenv("OAUTHLIB_INSECURE_TRANSPORT") or "").strip() == "1":
        return
    try:
        pu = urlparse(request.url)
        if pu.scheme == "http" and (pu.hostname or "").lower() in ("localhost", "127.0.0.1"):
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    except Exception:
        pass


def _append_query(url: str, params: dict[str, str]) -> str:
    sep = "&" if "?" in url else "?"
    return url + sep + urlencode(params)


@google_oauth_bp.get("/google/auth/<username>")
def google_auth_start(username: str):
    username = (username or "").strip().lower()
    if not username or len(username) > 256:
        abort(400)

    cred_path = get_client_secrets_path()
    if not cred_path.is_file():
        log.error("Missing OAuth client secrets at %s", cred_path)
        return (
            jsonify(
                {
                    "error": "missing_credentials_json",
                    "path": str(cred_path),
                    "hint": (
                        "Download OAuth client JSON from Google Cloud Console and save as "
                        "backend/credentials.json, or set GMAIL_CREDENTIALS_PATH. In container "
                        "deployments you can instead set GMAIL_CREDENTIALS_JSON (raw JSON) or "
                        "GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET (+ GOOGLE_PROJECT_ID, "
                        "GOOGLE_REDIRECT_URI) as environment variables."
                    ),
                }
            ),
            503,
        )

    expo_redirect = (request.args.get("expo_redirect") or "").strip() or default_oauth_frontend_return_url()

    session["oauth_username"] = username
    session["oauth_expo_redirect"] = expo_redirect
    session.permanent = True

    redirect_uri = _redirect_uri()
    log.info("[OAuth] start username=%s redirect_uri=%s", username, redirect_uri)

    try:
        flow = Flow.from_client_secrets_file(
            str(cred_path),
            scopes=SCOPES,
            redirect_uri=redirect_uri,
            **_FLOW_KWARGS,
        )
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
        )
    except Exception as e:
        log.exception("Failed to build OAuth flow: %s", e)
        return jsonify({"error": "oauth_flow_build_failed", "detail": str(e)}), 500

    session["oauth_state"] = state
    log.info("[OAuth] redirect user=%s to Google", username)
    return redirect(authorization_url)


@google_oauth_bp.get("/google/oauth2callback")
def google_oauth_callback():
    err = request.args.get("error")
    expo_redirect = session.get("oauth_expo_redirect") or default_oauth_frontend_return_url()

    if err:
        session.pop("oauth_username", None)
        session.pop("oauth_expo_redirect", None)
        session.pop("oauth_state", None)
        log.warning("[OAuth] Google returned error=%s", err)
        return redirect(
            _append_query(
                expo_redirect,
                {"gmail_oauth_error": err},
            )
        )

    if request.args.get("state") != session.get("oauth_state"):
        log.warning("[OAuth] state mismatch")
        abort(400, "Invalid OAuth state")

    cred_path = get_client_secrets_path()
    if not cred_path.is_file():
        abort(503, "credentials file missing")

    username = session.get("oauth_username") or ""

    _enable_oauthlib_http_for_local_callback()

    try:
        flow = Flow.from_client_secrets_file(
            str(cred_path),
            scopes=SCOPES,
            redirect_uri=_redirect_uri(),
            **_FLOW_KWARGS,
        )
        # Google redirects to the same host/scheme as in the auth request; redirect_uri must match.
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        log.exception("[OAuth] token exchange failed: %s", e)
        session.pop("oauth_username", None)
        session.pop("oauth_expo_redirect", None)
        session.pop("oauth_state", None)
        return redirect(
            _append_query(
                expo_redirect,
                {"gmail_oauth_error": "token_exchange_failed", "detail": quote(str(e), safe="")},
            )
        )

    creds = flow.credentials
    session.pop("oauth_state", None)
    session.pop("oauth_expo_redirect", None)
    session.pop("oauth_username", None)

    try:
        save_google_credentials(username or None, creds)
    except Exception as e:
        log.exception("[OAuth] failed to save token: %s", e)
        return redirect(
            _append_query(
                expo_redirect,
                {"gmail_oauth_error": "save_token_failed", "detail": quote(str(e), safe="")},
            )
        )

    log.info("[OAuth] success for user=%s", username)
    return redirect(
        _append_query(
            expo_redirect,
            {
                "gmail_oauth": "1",
                "oauth_username": username,
            },
        )
    )


@google_oauth_bp.post("/api/google-profile")
def google_profile():
    """Return Gmail address for the stored token (single-account ``token.json``)."""
    body = request.get_json(silent=True) or {}
    _ = (body.get("user_id") or "").strip()

    email = _stored_gmail_email()
    return jsonify({"email": email}), 200


@google_oauth_bp.post("/api/email-connections")
def email_connections():
    """
    Provider connection flags for the chat UI.

    This backend uses a single ``token.json`` (not per ``user_id``). If a token exists and is
    valid, Gmail is reported connected so the app shows the linked address after OAuth.
    """
    body = request.get_json(silent=True) or {}
    _ = (body.get("user_id") or "").strip()

    gmail_email = _stored_gmail_email()
    gmail_connected = bool(gmail_email)
    return jsonify(
        {
            "gmail_connected": gmail_connected,
            "gmail_email": gmail_email,
            "outlook_connected": False,
            "outlook_email": None,
        }
    ), 200
