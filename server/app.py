#!/usr/bin/env python3
"""Serve dashboard static files + live data scraper API."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from pathlib import Path

import urllib3
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from scrapers import SCRAPERS, fetch_all_live_data

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = Path(__file__).resolve().parent.parent

app = Flask(__name__)
CORS(app)

_lock = threading.Lock()
_payload: dict | None = None
_inflight = None
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="live-scrape")


def _warming_payload() -> dict:
    return {
        "status": "warming",
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {"total": len(SCRAPERS), "ok": 0, "failed": 0},
        "sources": {},
    }


def _store_fetch() -> dict:
    global _payload, _inflight
    try:
        data = fetch_all_live_data()
        data["status"] = "ok"
        with _lock:
            _payload = data
            _inflight = None
        return data
    except Exception as exc:  # noqa: BLE001
        failed = {
            "status": "error",
            "error": str(exc),
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "summary": {"total": len(SCRAPERS), "ok": 0, "failed": len(SCRAPERS)},
            "sources": {},
        }
        with _lock:
            if _payload is None:
                _payload = failed
            _inflight = None
        return _payload or failed


def get_live(force: bool = False, wait: float = 50.0) -> dict:
    """Return cached live data; kick off a scrape if needed."""
    global _inflight
    with _lock:
        if _payload is not None and not force:
            return _payload
        if _inflight is None:
            _inflight = _pool.submit(_store_fetch)
        fut = _inflight
        cached = _payload

    if cached is not None and not force:
        return cached

    try:
        return fut.result(timeout=wait)
    except FuturesTimeout:
        return cached if cached is not None else _warming_payload()


def _warm_on_boot() -> None:
    try:
        get_live(force=True, wait=90)
    except Exception:
        pass


threading.Thread(target=_warm_on_boot, daemon=True, name="warm-live").start()


@app.route("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.route("/health")
def health():
    with _lock:
        cached = _payload is not None
    return jsonify({"ok": True, "cached": cached})


@app.route("/api/live-data")
def live_data():
    force = request.args.get("refresh") in {"1", "true", "yes"}
    wait = 8.0 if force else 50.0
    if force:
        threading.Thread(target=lambda: get_live(force=True, wait=90), daemon=True).start()
        with _lock:
            if _payload is not None:
                out = dict(_payload)
                out["refreshing"] = True
                return jsonify(out)
        return jsonify(_warming_payload())
    return jsonify(get_live(force=False, wait=wait))


@app.route("/api/live-data/refresh")
def live_data_refresh():
    threading.Thread(target=lambda: get_live(force=True, wait=90), daemon=True).start()
    with _lock:
        if _payload is not None:
            out = dict(_payload)
            out["refreshing"] = True
            return jsonify(out)
    return jsonify(_warming_payload())


@app.route("/css/<path:filename>")
def css_files(filename):
    return send_from_directory(ROOT / "css", filename)


@app.route("/js/<path:filename>")
def js_files(filename):
    return send_from_directory(ROOT / "js", filename)


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/<path:path>")
def other_static(path):
    target = ROOT / path
    if target.is_file():
        return send_from_directory(ROOT, path)
    return "Not found", 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"Serving from: {ROOT}")
    print(f"Dashboard: http://0.0.0.0:{port}/")
    print(f"Live API:  http://0.0.0.0:{port}/api/live-data")
    app.run(host="0.0.0.0", port=port, debug=False)
