import os
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


def _get_credentials_path() -> Path:
    return _resolve_config_path("GMAIL_CREDENTIALS_PATH", DEFAULT_BACKEND_CREDENTIALS_PATH)


def get_client_secrets_path() -> Path:
    """OAuth client JSON path (``credentials.json`` / ``GMAIL_CREDENTIALS_PATH``)."""
    return _get_credentials_path()


def load_google_credentials(user_id: Optional[str] = None) -> Optional[Credentials]:
    """Load stored Gmail OAuth credentials (single ``token.json``; ``user_id`` is unused for now)."""
    _ = user_id
    token_path = _get_token_path()
    if not token_path.exists():
        return None
    try:
        return Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception:
        return None


def save_google_credentials(user_id: Optional[str], creds: Credentials) -> None:
    """Persist Gmail OAuth credentials to the configured token path."""
    _ = user_id
    token_path = _get_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())


def get_gmail_service():
    token_path = _get_token_path()
    credentials_path = _get_credentials_path()
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not credentials_path.exists():
            raise RuntimeError(
                "Missing Google OAuth credentials file. "
                f"Tried: {credentials_path} (set GMAIL_CREDENTIALS_PATH to override)"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path),
            SCOPES,
        )
        # For "web" OAuth clients, Google requires the redirect URI to match exactly.
        # `run_local_server()` uses `http://localhost:<port>/`, so we allow pinning the port.
        # Add `http://localhost:<port>/` to your OAuth client's Authorized redirect URIs.
        port_raw = (os.getenv("GMAIL_OAUTH_LOCAL_SERVER_PORT") or "").strip()
        port = int(port_raw) if port_raw else 0
        creds = flow.run_local_server(port=port)

        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds)
    return service