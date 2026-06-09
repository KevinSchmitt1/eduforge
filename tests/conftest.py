"""Pytest configuration for the forged test suite.

Loads the project .env file (if present) before any test runs, so tests that
exercise the real LLM path can find OPENAI_API_KEY without extra setup.
Keys already present in the environment are never overwritten.
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — no external dependencies required."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


# Load .env from project root (the directory containing this tests/ folder)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_load_dotenv(_PROJECT_ROOT / ".env")
