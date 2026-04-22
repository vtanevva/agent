"""
Classification sanity check (SQLite / backend services era).

Run from repo root:
    python tests/test_classification.py

Uses the same classifier stack as HTTP ``POST /debug/classify_ai`` (no Mongo).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _bootstrap_backend_path() -> None:
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    p = str(backend)
    if p not in sys.path:
        sys.path.insert(0, p)


def main() -> None:
    _bootstrap_backend_path()
    from services.classification_context import build_classification_input
    from services.classifier_ai import classify

    sample = (
        "Hi — can you send the signed ACME contract back by 5pm today? "
        "Board needs it for the call."
    )
    enriched = build_classification_input(
        raw_message_text=sample,
        client_name="ACME",
        project_name=None,
        project_context=None,
    )
    out = classify(enriched, raw_text=sample) or {}
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
