from __future__ import annotations

from typing import Any

from services.unified_processor import process_normalized_message


def handle_normalized_event(normalized: dict[str, Any]) -> dict[str, Any]:
    """Shared event orchestration entrypoint for Slack/Gmail/etc."""
    return process_normalized_message(normalized)

