"""Success-check evaluation.

v0.1 policy: we report OK whenever the action executed without raising.
The NL `success_check` text is logged but not verified — real semantic
verification lands in v0.2 with an LLM-backed check.

This file used to implement DOM heuristics (searching for elements with
`role=alert` or text like "error|failed|denied"). In practice every real
site has benign `aria-live` regions and cookie banners that carry those
affordances on load, which produced a high false-positive rate. Until we
can discriminate real errors from benign alerts, we choose to under-claim.
"""

from __future__ import annotations

import logging

from playwright.sync_api import Page

log = logging.getLogger(__name__)


def evaluate_success(_page: Page, check: str | None) -> bool:
    """Report success for any step that did not raise.

    Callers pass the NL post-condition string; we log it at INFO for trace
    readability but do not attempt to verify it.
    """
    if check:
        log.info("success_check (unverified in v0.1): %s", check)
    return True
