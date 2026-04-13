"""Tiered grounding: find the element on the current page matching a RecipeStep.

Tier 1 (always): structural lookup via Playwright's `get_by_role` etc. Free.
Tier 2 (planned v0.2): ARIA-snapshot + Haiku 4.5 disambiguation. ~$0.005/step.
Tier 3 (planned v0.3): set-of-marks vision. Reserved for failures of tier 2.

v0.1 ships Tier 1 only with a short attach-wait (GROUNDING_WAIT_MS) — a human
would pause for the element to render after a page transition; so do we.
"""

from __future__ import annotations

import logging
import time

from playwright.sync_api import Locator, Page

from understudy.types import ActionType, RecipeStep

log = logging.getLogger(__name__)

TEXTBOX_ROLES = {"textbox", "searchbox", "combobox"}
CLICKABLE_ROLES = {"button", "link", "menuitem", "tab"}
NO_TARGET_ACTIONS = {ActionType.NAV, ActionType.WAIT, ActionType.NOTE, ActionType.KEY}

# How long grounding will poll for a matching element to appear before giving
# up. Kept modest so genuine misses still fail fast at the CLI.
GROUNDING_WAIT_MS = 3000
GROUNDING_POLL_MS = 150


class GroundingError(RuntimeError):
    """The step's target could not be located on the current page."""


def ground(page: Page, step: RecipeStep) -> Locator | None:
    """Locate the element for `step` on `page`.

    Returns None when the step has no target (nav/wait/note/key-without-target).
    Raises GroundingError when the target should exist but can't be found
    within `GROUNDING_WAIT_MS` of polling.
    """
    if step.action in NO_TARGET_ACTIONS and not step.aria_name:
        return None
    role = (step.aria_role or "").lower()
    name = step.aria_name or ""

    deadline = time.monotonic() + (GROUNDING_WAIT_MS / 1000)
    last_tried: list[str] = []
    while True:
        result, tried = _try_locate(page, role, name)
        last_tried = tried
        if result is not None:
            return result
        if time.monotonic() >= deadline:
            break
        time.sleep(GROUNDING_POLL_MS / 1000)

    raise GroundingError(
        f"step {step.idx}: could not locate {role or '<no-role>'}[{name!r}] "
        f"within {GROUNDING_WAIT_MS}ms; tried: {', '.join(last_tried)}"
    )


def _try_locate(page: Page, role: str, name: str) -> tuple[Locator | None, list[str]]:
    tried: list[str] = []

    if role and name:
        loc = page.get_by_role(role, name=name, exact=True)  # type: ignore[arg-type]
        tried.append(f"role={role}[name={name!r},exact]")
        c = loc.count()
        if c == 1:
            return loc, tried

        loc = page.get_by_role(role, name=name)  # type: ignore[arg-type]
        tried.append(f"role={role}[name~={name!r}]")
        c = loc.count()
        if c == 1:
            return loc, tried
        if c > 1:
            vis = _first_visible(loc)
            if vis is not None:
                tried.append("filter=visible")
                return vis, tried

    if role in TEXTBOX_ROLES and name:
        for label, fn in (
            ("get_by_label", page.get_by_label),
            ("get_by_placeholder", page.get_by_placeholder),
        ):
            alt = fn(name)
            tried.append(label)
            if alt.count() >= 1:
                return alt.first, tried

    if role in CLICKABLE_ROLES and name:
        # The recipe's role may be wrong (e.g. site renders a tab as a link).
        # Re-try every clickable role with the same name before giving up.
        for alt_role in sorted(CLICKABLE_ROLES - {role}):
            alt = page.get_by_role(alt_role, name=name)  # type: ignore[arg-type]
            tried.append(f"alt-role={alt_role}")
            c = alt.count()
            if c == 1:
                return alt, tried
            if c > 1:
                vis = _first_visible(alt)
                if vis is not None:
                    return vis, tried

        alt = page.get_by_text(name, exact=False)
        tried.append("get_by_text")
        if alt.count() >= 1:
            return alt.first, tried

    return None, tried


def _first_visible(loc: Locator) -> Locator | None:
    count = loc.count()
    for i in range(count):
        candidate = loc.nth(i)
        try:
            if candidate.is_visible(timeout=200):
                return candidate
        except Exception as e:
            log.debug("visibility probe failed on index %d: %s", i, e)
    return None
