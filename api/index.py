"""Vercel WSGI entry — Flask app lives in server/app.py."""

import sys
from pathlib import Path

_SERVER = Path(__file__).resolve().parent.parent / "server"
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from app import app  # noqa: E402

__all__ = ["app"]
