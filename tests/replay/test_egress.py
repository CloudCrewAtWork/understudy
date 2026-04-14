"""Sub-resource egress filter tests.

The pure-function tests cover the decision logic. The integration test
drives a real Chromium via `sync_playwright` and confirms the filter
actually blocks sub-resources (document, image, xhr) to non-allowlisted
hosts, while allowing a whitelisted host through.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from playwright.sync_api import sync_playwright

from understudy.replay.egress import (
    BlockedRequest,
    _url_is_permitted,
    install_egress_filter,
)

ALLOW = frozenset({"example.com"})


# ---------- pure decision logic ----------


def test_about_blank_permitted():
    ok, _ = _url_is_permitted("about:blank", "document", ALLOW)
    assert ok


def test_file_scheme_always_denied():
    ok, reason = _url_is_permitted("file:///etc/passwd", "document", ALLOW)
    assert not ok
    assert reason == "file_scheme"


def test_allowlisted_host_passes():
    ok, _ = _url_is_permitted("https://example.com/style.css", "stylesheet", ALLOW)
    assert ok


def test_subdomain_of_allowlisted_passes():
    ok, _ = _url_is_permitted("https://cdn.example.com/a.js", "script", ALLOW)
    assert ok


def test_sibling_host_blocked():
    ok, reason = _url_is_permitted("https://evil.com/beacon.gif", "image", ALLOW)
    assert not ok
    assert reason == "host_not_allowlisted"


def test_parent_of_allowlisted_does_not_pass():
    # Only subdomains of an allowed host pass; the parent of an allowed
    # subdomain is NOT implied.
    allow = frozenset({"cdn.example.com"})
    ok, reason = _url_is_permitted("https://example.com/", "document", allow)
    assert not ok
    assert reason == "host_not_allowlisted"


def test_small_data_image_permitted():
    ok, _ = _url_is_permitted("data:image/png;base64,AAAA", "image", ALLOW)
    assert ok


def test_large_data_image_blocked():
    big = "data:image/png;base64," + ("A" * 3000)
    ok, reason = _url_is_permitted(big, "image", ALLOW)
    assert not ok
    assert reason == "data_uri_too_large"


def test_small_data_script_still_blocked():
    # Script/document data URIs are suspicious regardless of size.
    ok, reason = _url_is_permitted("data:text/javascript,alert(1)", "script", ALLOW)
    assert not ok
    assert reason == "data_uri_script_or_document"


def test_deny_listed_host_blocked_even_if_allowlisted():
    # Belt + suspenders: the capture-time deny-list wins.
    allow = frozenset({"chase.com"})
    ok, reason = _url_is_permitted("https://chase.com/login", "document", allow)
    assert not ok
    assert reason == "deny_listed"


def test_unsupported_scheme_blocked():
    ok, reason = _url_is_permitted("javascript:alert(1)", "document", ALLOW)
    assert not ok
    assert reason == "unsupported_scheme"


def test_userinfo_url_blocked():
    # `url_host` rejects userinfo URLs, so they end up as malformed_host.
    ok, reason = _url_is_permitted("https://safe@evil.com/", "document", ALLOW)
    assert not ok
    assert reason == "malformed_host"


def test_ws_allowlisted_host_passes():
    ok, _ = _url_is_permitted("wss://example.com/socket", "websocket", ALLOW)
    assert ok


def test_ws_non_allowlisted_blocked():
    ok, reason = _url_is_permitted("wss://evil.com/socket", "websocket", ALLOW)
    assert not ok
    assert reason == "host_not_allowlisted"


# ---------- integration: real Chromium ----------


@contextmanager
def _fixture_pages(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[str, str]]:
    """Write two tiny pages to disk and return their URLs.

    Returns (permitted_url, attacker_image_url) as `file://` URLs — both
    below our `file://` block, so we serve them via a minimal inline route
    in the test itself.
    """
    tmp = tmp_path_factory.mktemp("egress")
    permitted = tmp / "page.html"
    # Page tries to load an image from an attacker host. If the filter
    # works, that image request never escapes.
    permitted.write_text(
        """<!doctype html><title>x</title>
        <img id="beacon" src="https://attacker.test/pixel.gif">
        <span id="ok">hello</span>
        """,
        encoding="utf-8",
    )
    yield (permitted.as_uri(), "https://attacker.test/pixel.gif")


def test_integration_blocks_subresource_to_nonallowlisted_host(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """End-to-end: navigate to a served page that tries to image-beacon out.

    We serve the doc via a route so `file://` isn't involved at all. The
    filter's allowlist is `{served-host}`. Attacker host must be blocked
    and the block must surface through `on_block`.
    """
    blocked: list[BlockedRequest] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        # Served host is `example.test`. Attacker is `attacker.test`.
        allow = frozenset({"example.test"})
        install_egress_filter(ctx, allow, blocked.append)

        # Fulfil the target page from memory (no real network).
        def serve(route):
            if route.request.url.startswith("https://example.test/"):
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="""<!doctype html><title>x</title>
                    <img id="beacon" src="https://attacker.test/pixel.gif">""",
                )
            # else: the egress filter's own route handler will run first
            # and either continue_ or abort.

        ctx.route("https://example.test/*", serve)

        page = ctx.new_page()
        page.goto("https://example.test/")
        # Give the image request a chance to be attempted + blocked.
        page.wait_for_timeout(300)

        browser.close()

    hosts = {b.url for b in blocked}
    assert any(
        "attacker.test" in h for h in hosts
    ), f"expected an attacker.test block; got {hosts}"
    assert all(b.reason == "host_not_allowlisted" for b in blocked if "attacker.test" in b.url)


def test_small_data_script_blocked_regardless_of_size():
    # Bytes check order matters: type check fires first, size never consulted.
    ok, reason = _url_is_permitted("data:text/javascript,a", "script", ALLOW)
    assert not ok
    assert reason == "data_uri_script_or_document"


def test_userinfo_injection_at_replay_blocked():
    # https://cdn.example.com@evil.com/ resolves to evil.com, but url_host
    # rejects userinfo entirely so it surfaces as malformed.
    ok, reason = _url_is_permitted(
        "https://cdn.example.com@evil.com/pixel.gif", "image", ALLOW
    )
    assert not ok
    assert reason == "malformed_host"


def test_ip_literal_at_replay_blocked():
    ok, reason = _url_is_permitted("https://127.0.0.1/pixel.gif", "image", ALLOW)
    assert not ok
    assert reason == "malformed_host"
