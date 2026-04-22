"""
HTTP client for the core backend service living in /backend.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import requests

from backend.utils.logger import get_logger

logger = get_logger("core_backend_client")

DEFAULT_TIMEOUT_SECONDS = 15


def _core_base_url() -> str:
    return (os.getenv("CORE_BACKEND_URL") or "http://localhost:5000").rstrip("/")


def _post_json(path: str, payload: Dict[str, Any], *, timeout_s: int = DEFAULT_TIMEOUT_SECONDS) -> Dict[str, Any]:
    base = _core_base_url()
    url = f"{base}/{path.lstrip('/')}"
    try:
        resp = requests.post(url, json=payload, timeout=timeout_s)
    except Exception as e:
        logger.error("Core backend request failed: url=%s error=%s", url, e, exc_info=True)
        return {"success": False, "error": str(e), "core_backend_url": base, "path": path}

    try:
        data = resp.json()
    except Exception:
        data = {"raw": (resp.text or "")[:4000]}

    if resp.status_code >= 400:
        return {
            "success": False,
            "status_code": resp.status_code,
            "error": data.get("error") if isinstance(data, dict) else "core_backend_error",
            "response": data,
            "core_backend_url": base,
            "path": path,
        }

    if isinstance(data, dict):
        data.setdefault("success", True)
        return data

    return {"success": True, "response": data}


def ingest_gmail(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _post_json("/ingest/gmail", payload)


def ingest_slack(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _post_json("/ingest/slack", payload)


def gmail_pubsub(envelope: Dict[str, Any]) -> Dict[str, Any]:
    return _post_json("/webhooks/gmail/pubsub", envelope)


def fetch_recent_messages(
    *,
    user_id: str = "",
    limit: int = 25,
    source: str = "gmail",
    timeout_s: int = DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """GET /api/messages/recent — newest ingested rows for chat/email listing."""
    base = _core_base_url()
    url = f"{base}/api/messages/recent"
    params: Dict[str, Any] = {"limit": max(1, min(int(limit), 100)), "source": source or "gmail"}
    if (user_id or "").strip():
        params["user_id"] = user_id.strip()
    try:
        resp = requests.get(url, params=params, timeout=timeout_s)
    except Exception as e:
        logger.error("Core backend GET failed: url=%s error=%s", url, e, exc_info=True)
        return {"success": False, "error": str(e), "core_backend_url": base, "path": "/api/messages/recent"}

    try:
        data = resp.json()
    except Exception:
        data = {"raw": (resp.text or "")[:4000]}

    if resp.status_code >= 400:
        return {
            "success": False,
            "status_code": resp.status_code,
            "error": data.get("error") if isinstance(data, dict) else "core_backend_error",
            "response": data,
            "core_backend_url": base,
            "path": "/api/messages/recent",
        }

    if isinstance(data, dict):
        data.setdefault("success", True)
        return data

    return {"success": True, "response": data}

