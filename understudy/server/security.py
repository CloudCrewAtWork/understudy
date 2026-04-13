"""Security middleware for the local UI server.

Defensive controls:

- **Bind 127.0.0.1 only** is enforced at the CLI launch layer, not here.
- **CSRF token** — minted at server start, embedded in the launch URL,
  required in the `X-Understudy-CSRF` header on every mutating request.
- **Origin / Sec-Fetch-Site** — cross-site requests are refused.
- **Host allowlist** — `Host` header must be `127.0.0.1:<port>` or
  `localhost:<port>`. Defends against DNS rebinding.
- **Content security policy** — on every HTML response.

The token is a 256-bit urlsafe string, compared in constant time.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

log = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "x-understudy-csrf"


def mint_token() -> str:
    return secrets.token_urlsafe(32)


class SessionSecurity:
    """Holds the per-session CSRF token + the allowed Host/Origin values."""

    def __init__(self, csrf_token: str, host: str, port: int) -> None:
        self.csrf_token = csrf_token
        # Both 127.0.0.1 and localhost resolve to the same loopback; accept both.
        self.allowed_hosts: frozenset[str] = frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})
        self.allowed_origins: frozenset[str] = frozenset(
            {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
        )


class SecurityMiddleware(BaseHTTPMiddleware):
    """Enforces Host, Origin/Sec-Fetch-Site, and CSRF on the request path."""

    def __init__(self, app, session: SessionSecurity) -> None:
        super().__init__(app)
        self.session = session

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        method = request.method.upper()
        host_hdr = (request.headers.get("host") or "").lower()
        origin = request.headers.get("origin")
        sec_fetch_site = request.headers.get("sec-fetch-site")

        # Host allowlist: defends DNS rebinding even when Origin is valid.
        if host_hdr not in self.session.allowed_hosts:
            log.warning("refused request: bad Host %r", host_hdr)
            return _forbid("bad host")

        # Origin check for cross-site: browsers set Origin on any fetch.
        # We allow missing Origin for same-origin GET/HEAD (some browsers omit it).
        if origin is not None and origin not in self.session.allowed_origins:
            log.warning("refused request: bad Origin %r", origin)
            return _forbid("bad origin")

        # Sec-Fetch-Site is stronger: the browser tells us the relationship
        # between the request origin and the target. Only same-origin or
        # top-level navigations may mutate.
        if method not in SAFE_METHODS:
            if sec_fetch_site and sec_fetch_site not in {"same-origin", "same-site"}:
                log.warning("refused mutation: sec-fetch-site=%r", sec_fetch_site)
                return _forbid("cross-site mutation")

            token = request.headers.get(CSRF_HEADER)
            if not token or not secrets.compare_digest(token, self.session.csrf_token):
                return _forbid("bad csrf token")

        response = await call_next(request)
        _apply_hardening_headers(response)
        return response


def _forbid(detail: str) -> Response:
    return JSONResponse(status_code=403, content={"detail": detail})


def _apply_hardening_headers(response: Response) -> None:
    # Content-Security-Policy: prevent script/image/frame from anywhere
    # except ourselves. No inline scripts. No eval.
    response.headers.setdefault(
        "content-security-policy",
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "base-uri 'self'",
    )
    response.headers.setdefault("x-frame-options", "DENY")
    response.headers.setdefault("x-content-type-options", "nosniff")
    response.headers.setdefault("referrer-policy", "no-referrer")
    response.headers.setdefault("permissions-policy", "interest-cohort=()")
