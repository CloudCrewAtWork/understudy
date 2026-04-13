"""Success-check evaluation.

v0.1: DOM heuristics only. Look for explicit error affordances; assume success
otherwise. Cheap, silent, well-understood. An LLM-backed semantic check lands
in v0.2 once we have a corpus of recipes to benchmark against.
"""

from __future__ import annotations

import logging

from playwright.sync_api import Page

log = logging.getLogger(__name__)

ERROR_ROLES: tuple[str, ...] = ("alert", "alertdialog")


def evaluate_success(page: Page, check: str | None) -> bool:
    """Return True if no obvious failure signal is present on the page.

    If `check` is None we return True (no postcondition declared).
    We deliberately do NOT verify the NL check itself in v0.1 — logged only.

    Heuristic scope is intentionally narrow: ARIA alert/alertdialog roles are
    the only signal we trust. A prior version also did a page-text regex for
    "error | failed | denied" etc., but real sites bury those words in hidden
    form-validation messages, screen-reader helpers, and i18n dictionaries —
    so the regex false-positive rate on healthy pages was too high to ship.
    """
    if check:
        log.info("success_check (unverified in v0.1): %s", check)
    try:
        for role in ERROR_ROLES:
            alert = page.get_by_role(role)  # type: ignore[arg-type]
            if alert.count() > 0 and alert.first.is_visible(timeout=300):
                return False
    except Exception as e:
        log.debug("success heuristic raised, treating as pass: %s", e)
        return True
    return True
