import json
import os
import tempfile
from pathlib import Path
from typing import Optional

try:
    # Ensures `backend/.env` is loaded even when running `python -c ...`
    # (otherwise env vars like GMAIL_OAUTH_LOCAL_SERVER_PORT won't be picked up).
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = [
    # Required for Pub/Sub watch + History API processing:
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.readonly",
    # Draft creation:
    "https://www.googleapis.com/auth/gmail.compose",
    # Primary calendar: list + create events (weekly schedule + invitations). Re-consent after scope changes.
    "https://www.googleapis.com/auth/calendar.events",
]

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent

DEFAULT_BACKEND_TOKEN_PATH = BASE_DIR / "token.json"
DEFAULT_BACKEND_CREDENTIALS_PATH = BASE_DIR / "credentials.json"


def _resolve_config_path(env_var: str, default_path: Path) -> Path:
    raw = os.getenv(env_var)
    if not raw:
        return default_path

    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (REPO_DIR / p).resolve()
    return p


def _get_token_path() -> Path:
    return _resolve_config_path("GMAIL_TOKEN_PATH", DEFAULT_BACKEND_TOKEN_PATH)


def _user_token_path(user_id: Optional[str]) -> Path:
    """
    Resolve token path for a specific app user.

    - No user_id -> legacy shared ``token.json``
    - user_id    -> ``token_<normalized_user_id>.json`` in the same directory
    """
    base = _get_token_path()
    uid = (user_id or "").strip().lower()
    if not uid:
        return base
    safe_uid = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in uid)
    return base.with_name(f"{base.stem}_{safe_uid}{base.suffix}")


def _get_credentials_path() -> Path:
    return _resolve_config_path("GMAIL_CREDENTIALS_PATH", DEFAULT_BACKEND_CREDENTIALS_PATH)


def _build_client_config_from_env() -> Optional[dict]:
    """Build an OAuth client-secrets dict from environment variables.

    Supports two forms:
    - ``GMAIL_CREDENTIALS_JSON`` — raw JSON content of the client-secrets file.
    - ``GOOGLE_CLIENT_ID`` + ``GOOGLE_CLIENT_SECRET`` (+ optional ``GOOGLE_PROJECT_ID``,
      ``GOOGLE_REDIRECT_URI`` / ``OAUTH_REDIRECT_URI``) — synthesized Web client config.

    Returns ``None`` when no env-based configuration is available.
    """
    raw = os.getenv("GMAIL_CREDENTIALS_JSON")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass

    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        return None

    project_id = (os.getenv("GOOGLE_PROJECT_ID") or "").strip()

    path = "/google/oauth2callback"
    redirect_uris: list[str] = []

    def _add_redirect(u: str) -> None:
        u = u.split("?", 1)[0].strip().rstrip("/")
        if u.endswith(path):
            full = u
        else:
            full = f"{u.rstrip('/')}{path}"
        if full not in redirect_uris:
            redirect_uris.append(full)

    for key in ("GOOGLE_OAUTH_REDIRECT_URI", "GOOGLE_REDIRECT_URI", "OAUTH_REDIRECT_URI"):
        v = (os.getenv(key) or "").strip()
        if v:
            _add_redirect(v)
    for key in ("PUBLIC_API_URL", "PRODUCTION_URL", "RAILWAY_URL"):
        v = (os.getenv(key) or "").strip()
        if not v:
            continue
        if "://" not in v:
            v = f"https://{v.lstrip('/')}"
        _add_redirect(v)

    if not redirect_uris:
        redirect_uris = ["http://localhost:5000/google/oauth2callback"]

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "project_id": project_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": redirect_uris,
        }
    }


def _ensure_client_secrets_file(path: Path) -> Path:
    """Ensure a client-secrets JSON file exists on disk.

    If ``path`` already exists, return it unchanged. Otherwise, try to synthesize
    one from environment variables and write it to ``path`` (or a temp file if
    the target directory is read-only, e.g. in some container runtimes).
    """
    if path.exists():
        return path

    config = _build_client_config_from_env()
    if not config:
        return path  # caller will surface the "missing file" error

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f)
        return path
    except OSError:
        tmp = Path(tempfile.gettempdir()) / "gmail_client_secret.json"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(config, f)
        return tmp


def get_client_secrets_path() -> Path:
    """OAuth client JSON path (``credentials.json`` / ``GMAIL_CREDENTIALS_PATH``).

    Falls back to materializing a client-secrets file from environment variables
    (``GMAIL_CREDENTIALS_JSON`` or ``GOOGLE_CLIENT_ID`` / ``GOOGLE_CLIENT_SECRET``)
    when the file is not present on disk — useful for Docker/Railway-style
    deployments where secrets live in env vars rather than mounted files.
    """
    return _ensure_client_secrets_file(_get_credentials_path())


def load_google_credentials(user_id: Optional[str] = None) -> Optional[Credentials]:
    """Load stored Gmail OAuth credentials for a specific app user."""
    token_path = _user_token_path(user_id)
    if not token_path.exists():
        return None
    try:
        return Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception:
        return None


def save_google_credentials(user_id: Optional[str], creds: Credentials) -> None:
    """Persist Gmail OAuth credentials to a user-scoped token path."""
    token_path = _user_token_path(user_id)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())


def get_linked_gmail_address(user_id: Optional[str] = None) -> Optional[str]:
    """Primary Gmail address for the OAuth token stored for this app user, or ``None``."""
    creds = load_google_credentials(user_id)
    if not creds:
        return None
    try:
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                save_google_credentials(user_id, creds)
    except Exception:
        return None
    if not creds.valid:
        return None
    try:
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        addr = (profile.get("emailAddress") or "").strip().lower()
        return addr or None
    except Exception:
        return None


def get_gmail_service():
    token_path = _get_token_path()
    creds = None

    # Try the default token.json first, then fall back to any token_*.json in the same dir.
    candidates = [token_path] + sorted(token_path.parent.glob(f"{token_path.stem}_*.json"))
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            c = Credentials.from_authorized_user_file(str(candidate), SCOPES)
            if c and c.refresh_token:
                creds = c
                token_path = candidate
                break
        except Exception:
            continue

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    if not creds or not creds.valid:
        raise RuntimeError(
            "No valid Gmail token. Authenticate via GET /google/auth/<username> "
            "then retry. Token path: " + str(token_path)
        )

    service = build("gmail", "v1", credentials=creds)
    return service