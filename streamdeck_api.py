"""Loopback HTTP API so Stream Deck (and other local tools) can start/stop watching."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from app import App

DEFAULT_PORT = 17321


class StreamDeckApi:
    def __init__(self, app: App, port: int = DEFAULT_PORT) -> None:
        self.app = app
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handler = _make_handler(self.app)
        try:
            self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        except OSError:
            self._httpd = None
            return
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None

    @property
    def running(self) -> bool:
        return self._httpd is not None


def _make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            self._handle()

        def do_POST(self) -> None:  # noqa: N802
            self._handle()

        def _handle(self) -> None:
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path == "/status":
                self._json(200, app.stream_deck_status())
                return
            if path == "/watch/start":
                self._command(app.api_start_watching)
                return
            if path == "/watch/stop":
                self._command(app.api_stop_watching)
                return
            if path == "/watch/toggle":
                self._command(app.api_toggle_watching)
                return
            self._json(404, {"ok": False, "error": "Unknown path"})

        def _command(self, fn) -> None:  # noqa: ANN001
            error = app.call_on_ui(fn)
            status = app.stream_deck_status()
            if error:
                status = {**status, "ok": False, "error": error}
                self._json(409, status)
                return
            self._json(200, {**status, "ok": True})

        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler
