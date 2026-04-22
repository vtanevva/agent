"""
Run HTTP services from the repo root (no manual ``cd backend``).

  python server.py core   # Core API — ``backend/core_app.py`` (:5000)
  python server.py ai     # AI chat — ``backend/ai_app.py`` (:5055)

Production: ``start.sh`` (``core_app:app``, cwd ``backend/``) and ``start-ai.sh``
(``backend.ai_app:app``, cwd repo root).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"


def main() -> None:
    p = argparse.ArgumentParser(description="Run Aivis HTTP services from repo root.")
    p.add_argument(
        "service",
        choices=("core", "ai"),
        help="core = SQLite/webhooks API; ai = orchestrator LLM service",
    )
    args = p.parse_args()

    if args.service == "core":
        rc = subprocess.call([sys.executable, str(BACKEND / "core_app.py")], cwd=str(BACKEND))
        raise SystemExit(rc)

    rc = subprocess.call([sys.executable, str(BACKEND / "ai_app.py")], cwd=str(ROOT))
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
