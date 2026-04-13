"""Static dispatch of ActionType → exactly one Playwright call.

No `getattr(locator, name)`, no `page.evaluate(string)`. Every callable below
is explicit and reviewable. Adding a new action verb requires editing this file.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import NamedTuple

from playwright.sync_api import Locator, Page

from understudy.types import ActionType, RecipeStep

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 8000


class ActionContext(NamedTuple):
    page: Page
    locator: Locator | None
    value: str
    step: RecipeStep


class ActionError(RuntimeError):
    """Raised when an action fails to execute (not a grounding issue)."""


def _do_nav(ctx: ActionContext) -> None:
    target = ctx.value or ctx.step.aria_name or ""
    if not target.startswith(("http://", "https://")):
        raise ActionError(f"nav requires a full URL, got {target!r}")
    ctx.page.goto(target, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)


def _require_locator(ctx: ActionContext) -> Locator:
    if ctx.locator is None:
        raise ActionError(f"action {ctx.step.action} requires a located element")
    return ctx.locator


def _do_click(ctx: ActionContext) -> None:
    loc = _require_locator(ctx)
    loc.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
    loc.click(timeout=DEFAULT_TIMEOUT_MS)


def _do_dblclick(ctx: ActionContext) -> None:
    loc = _require_locator(ctx)
    loc.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
    loc.dblclick(timeout=DEFAULT_TIMEOUT_MS)


def _do_type(ctx: ActionContext) -> None:
    loc = _require_locator(ctx)
    loc.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
    # `fill` is injection-safe: it writes the string, never evaluates it.
    loc.fill(ctx.value, timeout=DEFAULT_TIMEOUT_MS)


def _do_key(ctx: ActionContext) -> None:
    key = ctx.value
    if not key:
        raise ActionError("key action requires a value (e.g. 'Enter')")
    if ctx.locator is not None:
        ctx.locator.press(key, timeout=DEFAULT_TIMEOUT_MS)
    else:
        ctx.page.keyboard.press(key)


def _do_scroll(ctx: ActionContext) -> None:
    if ctx.locator is not None:
        ctx.locator.scroll_into_view_if_needed(timeout=DEFAULT_TIMEOUT_MS)
    else:
        ctx.page.mouse.wheel(0, 500)


def _do_wait(ctx: ActionContext) -> None:
    # Best-effort: wait for network idle, capped.
    try:
        ctx.page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT_MS)
    except Exception as e:
        log.debug("networkidle wait timed out: %s", e)


def _do_select(ctx: ActionContext) -> None:
    loc = _require_locator(ctx)
    loc.wait_for(state="visible", timeout=DEFAULT_TIMEOUT_MS)
    loc.select_option(ctx.value, timeout=DEFAULT_TIMEOUT_MS)


def _do_upload(_ctx: ActionContext) -> None:
    # File upload needs explicit HITL + path validation — out of scope for v0.1.
    raise ActionError("upload actions are not enabled in v0.1; see roadmap")


def _do_note(_ctx: ActionContext) -> None:
    # note steps are informational; no side effect.
    return None


DISPATCH: dict[ActionType, Callable[[ActionContext], None]] = {
    ActionType.NAV: _do_nav,
    ActionType.CLICK: _do_click,
    ActionType.DBLCLICK: _do_dblclick,
    ActionType.TYPE: _do_type,
    ActionType.KEY: _do_key,
    ActionType.SCROLL: _do_scroll,
    ActionType.WAIT: _do_wait,
    ActionType.SELECT: _do_select,
    ActionType.UPLOAD: _do_upload,
    ActionType.NOTE: _do_note,
}


def execute(ctx: ActionContext) -> None:
    """Dispatch `ctx.step.action` to its handler. Unknown action → error."""
    handler = DISPATCH.get(ctx.step.action)
    if handler is None:
        raise ActionError(f"no dispatch for action {ctx.step.action}")
    handler(ctx)
