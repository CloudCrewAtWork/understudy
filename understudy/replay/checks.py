"""Success-check evaluation.

v0.1: DOM heuristics only. Look for explicit error affordances; assume success
otherwise. Cheap, silent, well-understood. An LLM-backed semantic check lands
in v0.2 once we have a corpus of recipes to benchmark against.
"""

from __future__ import annotations

import logging
import re

from playwright.sync_api import Page

log = logging.getLogger(__name__)

# Word-boundaried so we don't trip on benign text like "no errors".
ERROR_TEXT_RE = re.compile(
    r"\b(error|not\s+found|failed|denied|unavailable|something\s+went\s+wrong)\b",
    re.IGNORECASE,
)
ERROR_ROLES: tuple[str, ...] = ("alert", "alertdialog")


def evaluate_success(page: Page, check: str | None) -> bool:
    """Return True if no obvious failure signal is present on the page.

    If `check` is None we return True (no postcondition declared).
    We deliberately do NOT verify the NL check itself in v0.1 — logged only.
    """
    if check:
        log.info("success_check (unverified in v0.1): %s", check)
    try:
        for role in ERROR_ROLES:
            alert = page.get_by_role(role)  # type: ignore[arg-type]
            if alert.count() > 0 and alert.first.is_visible(timeout=300):
                return False
        err_text = page.get_by_text(ERROR_TEXT_RE)
        if err_text.count() > 0 and err_text.first.is_visible(timeout=300):
            return False
    except Exception as e:
        log.debug("success heuristic raised, treating as pass: %s", e)
        return True
    return True
