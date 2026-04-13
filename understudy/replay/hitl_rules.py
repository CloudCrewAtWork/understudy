"""Rules that decide when the replay engine MUST pause for human confirmation.

Design: hitl_rules is consulted BEFORE every step. It is deny-biased:
any matching rule triggers a prompt, regardless of recipe metadata. The
recipe's own `requires_confirmation` flag is an additional OR — induction
can only add gates, never remove them.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from understudy.types import ActionType, RecipeStep

from .result import StepOutcome

DESTRUCTIVE_VERBS = (
    r"\b("
    r"send|submit|delete|remove|wipe|destroy|"
    r"pay|buy|purchase|order|checkout|"
    r"transfer|withdraw|cancel|refund|"
    r"publish|post|share|tweet|broadcast|"
    r"sign|agree|accept|confirm"
    r")\b"
)
DESTRUCTIVE_RE = re.compile(DESTRUCTIVE_VERBS, re.IGNORECASE)
HITL_HEARTBEAT_EVERY = 25


def must_confirm(
    step: RecipeStep,
    *,
    current_url: str | None,
    recipe_known_domains: frozenset[str],
    completed: list[StepOutcome],
) -> tuple[bool, str]:
    """Return (needs_confirmation, reason).

    reason is user-facing ("destructive verb in intent: 'send'") when True,
    empty string when False.
    """
    if step.requires_confirmation:
        return True, "recipe marked this step as requiring confirmation"
    if DESTRUCTIVE_RE.search(step.intent):
        return True, f"destructive intent: {step.intent!r}"
    if step.action == ActionType.NAV:
        target = step.aria_name or ""
        if target.startswith(("http://", "https://")):
            host = (urlparse(target).hostname or "").lower()
            if host and not any(host == d or host.endswith("." + d) for d in recipe_known_domains):
                return True, f"nav to new domain: {host}"
    if current_url:
        host = (urlparse(current_url).hostname or "").lower()
        if host and not any(host == d or host.endswith("." + d) for d in recipe_known_domains):
            return True, f"current page ({host}) is not in the recipe's known domains"
    if len(completed) > 0 and len(completed) % HITL_HEARTBEAT_EVERY == 0:
        return True, f"heartbeat check every {HITL_HEARTBEAT_EVERY} steps"
    return False, ""


def known_domains(nav_targets: list[str]) -> frozenset[str]:
    """Extract registered domains from recorded nav URLs in a recipe."""
    out: set[str] = set()
    for url in nav_targets:
        if not url or not url.startswith(("http://", "https://")):
            continue
        host = (urlparse(url).hostname or "").lower()
        if host:
            out.add(host)
    return frozenset(out)
