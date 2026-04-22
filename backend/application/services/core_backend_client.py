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


def _post_json(path: str, payload: Dict[str, Any], *, timeout_s: int = DEFAULT_TIMEOUT_SECONDS) -> Dict[str, Any]:
    base = (os.getenv("CORE_BACKEND_URL") or "http://localhost:5000").rstrip("/")
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

