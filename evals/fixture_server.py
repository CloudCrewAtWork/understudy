"""Tiny HTTP server for CI-safe eval fixtures.

`evals/fixtures/` holds the static HTML pages our harness replays against.
Tests and the `understudy eval` runner spin up a server on an ephemeral
loopback port and point recipes at it — that way the pass-rate table is
deterministic and does not depend on github.com being up (or on rate
limits, DOM churn, captchas, Cloudflare challenges).

The real-site tier (nightly, non-blocking) lives in a separate runner
that hits actual URLs; this module only serves the fixtures.
"""

from __future__ import annotations

import contextlib
import http.server
import socketserver
import threading
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Silent SimpleHTTPRequestHandler rooted at `FIXTURES_DIR`.

    Default logger spams stderr on every request which is useless noise in
    pytest output.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(FIXTURES_DIR), **kwargs)  # type: ignore[arg-type]

    def log_message(self, format: str, *args: object) -> None:
        return


class FixtureServer:
    """Context manager wrapping a threaded HTTP server on 127.0.0.1.

        with FixtureServer() as srv:
            url = srv.url_for("search.html")  # -> http://127.0.0.1:XXXXX/search.html
    """

    def __init__(self) -> None:
        self._httpd: socketserver.TCPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    def start(self) -> None:
        if self._httpd is not None:
            return
        # Port 0 = kernel picks an ephemeral port.
        self._httpd = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            with contextlib.suppress(Exception):
                self._httpd.shutdown()
                self._httpd.server_close()
        self._httpd = None
        self._thread = None

    @property
    def base_url(self) -> str:
        # We bind the TCP socket to 127.0.0.1 for isolation, but the URL uses
        # "localhost" because the replay-time egress filter refuses IP literals
        # as part of its URL-hardening policy (see
        # `understudy/security/allowlist.py:url_host`). Using a named host
        # still resolves to the loopback interface while passing egress
        # normalization.
        return f"http://localhost:{self.port}"

    def url_for(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def __enter__(self) -> FixtureServer:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()
