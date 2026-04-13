"""Tiered grounding: find the element on the current page matching a RecipeStep.

Tier 1 (always): structural lookup via Playwright's `get_by_role` etc. Free.
Tier 2 (planned v0.2): ARIA-snapshot + Haiku 4.5 disambiguation. ~$0.005/step.
Tier 3 (planned v0.3): set-of-marks vision. Reserved for failures of tier 2.

v0.1 ships Tier 1 only. The public `ground()` function takes a Page + step
and returns a Locator, or raises GroundingError.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from playwright.sync_api import Locator, Page

from understudy.types import ActionType, RecipeStep

log = logging.getLogger(__name__)

TEXTBOX_ROLES = {"textbox", "searchbox", "combobox"}
CLICKABLE_ROLES = {"button", "link", "menuitem", "tab"}
# Actions that don't require a located element.
NO_TARGET_ACTIONS = {ActionType.NAV, ActionType.WAIT, ActionType.NOTE, ActionType.KEY}


class GroundingError(RuntimeError):
    """The step's target could not be located on the current page."""


@dataclass
class GroundingTrace:
    tried: list[str]
    matched: int


def ground(page: Page, step: RecipeStep) -> Locator | None:
    """Locate the element for `step` on `page`.

    Returns None when the step has no target (nav/wait/note/key-without-target).
    Raises GroundingError when the target should exist but can't be found.
    """
    if step.action in NO_TARGET_ACTIONS and not step.aria_name:
        return None
    role = (step.aria_role or "").lower()
    name = step.aria_name or ""
    tried: list[str] = []

    if role and name:
        loc = page.get_by_role(role, name=name, exact=True)  # type: ignore[arg-type]
        tried.append(f"role={role}[name={name!r},exact]")
        c = loc.count()
        if c == 1:
            return loc

        loc = page.get_by_role(role, name=name)  # type: ignore[arg-type]
        tried.append(f"role={role}[name~={name!r}]")
        c = loc.count()
        if c == 1:
            return loc
        if c > 1:
            vis = _first_visible(loc)
            if vis is not None:
                tried.append("filter=visible")
                return vis

    if role in TEXTBOX_ROLES and name:
        for label, fn in (
            ("get_by_label", page.get_by_label),
            ("get_by_placeholder", page.get_by_placeholder),
        ):
            alt = fn(name)
            tried.append(label)
            if alt.count() >= 1:
                return alt.first

    if role in CLICKABLE_ROLES and name:
        alt = page.get_by_text(name, exact=False)
        tried.append("get_by_text")
        if alt.count() >= 1:
            return alt.first

    raise GroundingError(
        f"step {step.idx}: could not locate {role or '<no-role>'}[{name!r}]; "
        f"tried: {', '.join(tried)}"
    )


def _first_visible(loc: Locator) -> Locator | None:
    count = loc.count()
    for i in range(count):
        candidate = loc.nth(i)
        try:
            if candidate.is_visible(timeout=500):
                return candidate
        except Exception as e:
            log.debug("visibility probe failed on index %d: %s", i, e)
    return None
