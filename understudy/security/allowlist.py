"""Capture-time allowlist.

Browser scope: deny-list of hosts we will not capture from. Hardened against:
- punycode / IDNA mismatches
- userinfo injection (`https://chase.com@evil.com/`)
- raw IP literals (IPv4 dotted, IPv6, octal)
- subdomain-bypass via `chase.com.evil.com`

macOS scope (Week 2): bundle-ID allowlist.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

DENY_DOMAINS: frozenset[str] = frozenset(
    {
        # Password managers
        "1password.com",
        "bitwarden.com",
        "lastpass.com",
        "dashlane.com",
        "keepersecurity.com",
        # Identity
        "icloud.com",
        "accounts.google.com",
        "myaccount.google.com",
        "appleid.apple.com",
        "login.microsoftonline.com",
        "okta.com",
        "oktapreview.com",
        "auth0.com",
        # Banks (US-centric starter — extend per region in config)
        "wellsfargo.com",
        "chase.com",
        "bankofamerica.com",
        "citibank.com",
        "capitalone.com",
        "usbank.com",
        "discover.com",
        # Payments
        "paypal.com",
        "venmo.com",
        "stripe.com",
        "checkout.stripe.com",
        "plaid.com",
        "coinbase.com",
        "robinhood.com",
        # Cloud consoles
        "console.aws.amazon.com",
        "portal.azure.com",
        "console.cloud.google.com",
    }
)


def _normalize_host(host: str) -> str:
    h = host.strip().lower().rstrip(".")
    try:
        return h.encode("idna").decode("ascii")
    except UnicodeError:
        return h


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    # Octal / dotted bypass: 017700000001 etc.
    return bool(host.startswith("0") and host.replace(".", "").isdigit())


def is_allowed(url: str | None, *, extra_deny: frozenset[str] = frozenset()) -> bool:
    """True if we may capture this URL. Default-deny on parse failure."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    # Reject userinfo: prevents `https://safe.com@evil.com/` confusion.
    if parsed.username or parsed.password:
        return False
    raw_host = parsed.hostname
    if not raw_host:
        return False
    host = _normalize_host(raw_host)
    if not host:
        return False
    if _is_ip_literal(host):
        return False
    deny = DENY_DOMAINS | extra_deny
    return not any(host == d or host.endswith("." + d) for d in deny)
