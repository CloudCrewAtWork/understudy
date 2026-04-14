"""Sub-resource egress filter for the replay browser context.

Rationale (see README "Threat Model"): the v0.1 engine only gated top-frame
navigation. That leaves every `<img>`, `fetch()`, `<script>`, XHR, WebSocket,
and stylesheet free to talk to arbitrary origins — a zero-click exfil path if
an allow-listed origin is ever compromised (stored XSS, malicious ad, hijacked
CDN). This module closes that gap by routing every Playwright request through
an allowlist check keyed on the hosts captured during the original recording.

Allowlist policy:
- Exact host match or subdomain match against the recipe's captured origins.
- `about:blank` is always allowed (Playwright internal).
- `file://` is always denied.
- `data:` URIs pass for small sizes and non-document/script types; large
  data-scripts are a known smuggling channel.
- Every block is reported via the `on_block` callback — caller decides whether
  to log, abort the run, or escalate to HITL.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass

from playwright.sync_api import BrowserContext, Request, Route, WebSocket

from understudy.security import host_in_allowlist, is_allowed, url_host

# Large inline `data:` scripts are a known smuggling channel. We permit small
# data URIs (common for favicons, inline SVGs) but reject anything that could
# plausibly carry a payload.
_MAX_DATA_URI_BYTES = 2048

# Resource types for which a `data:` URI is suspicious even when small.
_DATA_URI_BLOCKED_TYPES: frozenset[str] = frozenset({"document", "script"})


@dataclass(frozen=True)
class BlockedRequest:
    """One sub-resource the egress filter refused. Fed to the run's drift log."""

    url: str
    resource_type: str
    reason: str


BlockCallback = Callable[[BlockedRequest], None]


def _url_is_permitted(url: str, resource_type: str, allowed: frozenset[str]) -> tuple[bool, str]:
    """Return (ok, reason). `reason` is only meaningful when ok is False."""
    if not url:
        return False, "empty_url"
    if url.startswith("about:"):
        return True, ""
    if url.startswith("file://"):
        return False, "file_scheme"
    if url.startswith("data:"):
        if resource_type in _DATA_URI_BLOCKED_TYPES:
            return False, "data_uri_script_or_document"
        if len(url.encode("utf-8", errors="ignore")) > _MAX_DATA_URI_BYTES:
            return False, "data_uri_too_large"
        return True, ""
    # Only http(s) and ws(s) make sense beyond this point.
    if not url.startswith(("http://", "https://", "ws://", "wss://")):
        return False, "unsupported_scheme"
    host = url_host(url)
    if host is None:
        return False, "malformed_host"
    # Belt + suspenders: capture-time deny-list still applies.
    if url.startswith(("http://", "https://")) and not is_allowed(url):
        return False, "deny_listed"
    if not host_in_allowlist(host, allowed):
        return False, "host_not_allowlisted"
    return True, ""


def install_egress_filter(
    ctx: BrowserContext,
    allowed_origins: frozenset[str],
    on_block: BlockCallback,
) -> None:
    """Attach the filter to `ctx`. All future pages inherit it.

    `allowed_origins` must be the normalized host set (use `url_host`) — this
    function does not re-normalize, so bad input = silent allow-all for that
    entry. The calling code is expected to pass the output of
    `recipe.allowed_origins` (already normalized at capture time).
    """

    def handle_route(route: Route) -> None:
        req: Request = route.request
        ok, reason = _url_is_permitted(req.url, req.resource_type, allowed_origins)
        if ok:
            route.continue_()
            return
        on_block(BlockedRequest(url=req.url, resource_type=req.resource_type, reason=reason))
        # `blockedbyclient` surfaces in the devtools network panel as the
        # standard ERR_BLOCKED_BY_CLIENT — distinguishable from actual errors.
        # Already-handled races swallow quietly; they mean the request was
        # cancelled elsewhere.
        with contextlib.suppress(Exception):
            route.abort("blockedbyclient")

    def handle_websocket(ws: WebSocket) -> None:
        ok, reason = _url_is_permitted(ws.url, "websocket", allowed_origins)
        if ok:
            return
        on_block(BlockedRequest(url=ws.url, resource_type="websocket", reason=reason))

    ctx.route("**/*", handle_route)
    # WebSocket is a page-level event, not a context event. Hook every page
    # the context opens — including ones that appear later (`target=_blank`,
    # window.open, etc.).
    ctx.on("page", lambda p: p.on("websocket", handle_websocket))
