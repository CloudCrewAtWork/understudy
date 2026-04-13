"""The replay engine itself.

Synchronous Playwright loop. Per-step:
  PENDING → CONFIRM_CHECK → GROUNDING → ACTING → CHECKING → DONE/FAIL

Security invariants enforced here:
  - Recipe is validated on load (schema + allowlist + step cap).
  - Domain drift is tripped by framenavigated to a non-known host.
  - Downloads are cancelled by default.
  - Dialogs (alert/prompt/beforeunload) are dismissed.
  - Ctrl-C triggers graceful abort with audit entry.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from playwright.sync_api import (
    BrowserContext,
    Download,
    Page,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import (
    Error as PWError,
)
from pydantic import ValidationError

from understudy.config import get_settings
from understudy.security.allowlist import is_allowed
from understudy.types import ActionType, Recipe, RecipeStep

from .actions import ActionContext, ActionError
from .actions import execute as execute_action
from .audit import etld1, hash_value, log_event
from .checks import evaluate_success
from .grounding import GroundingError, ground
from .hitl_rules import known_domains, must_confirm
from .result import AbortReason, ReplayResult, StepOutcome, StepStatus
from .substitute import MissingParamError, render_template

log = logging.getLogger(__name__)

MAX_STEPS = 200
MAX_COST_USD = 0.50
MAX_LLM_CALLS = 10

ConfirmFn = Callable[[RecipeStep, str, str], Literal["approve", "deny", "abort"]]


@dataclass
class Budget:
    max_usd: float = MAX_COST_USD
    max_calls: int = MAX_LLM_CALLS
    used_usd: float = 0.0
    used_calls: int = 0

    def over(self) -> bool:
        return self.used_usd > self.max_usd or self.used_calls > self.max_calls


class RecipeInvariantError(RuntimeError):
    """Raised when a Recipe fails safety invariants on load."""


class DomainDriftError(RuntimeError):
    """The live page navigated to a denied domain mid-run."""


def validate_recipe_invariants(recipe: Recipe) -> None:
    if len(recipe.steps) > MAX_STEPS:
        raise RecipeInvariantError(f"recipe exceeds {MAX_STEPS} steps")
    for step in recipe.steps:
        if step.action == ActionType.NAV:
            target = step.aria_name or ""
            if target.startswith(("http://", "https://")) and not is_allowed(target):
                raise RecipeInvariantError(
                    f"step {step.idx} navigates to a denied domain: {target}"
                )


def default_confirm(
    _step: RecipeStep,
    _reason: str,
    _detail: str,
) -> Literal["approve", "deny", "abort"]:
    """Fallback for tests and non-interactive runs: always deny."""
    return "deny"


class Replayer:
    def __init__(
        self,
        recipe: Recipe,
        params: dict[str, str],
        *,
        headed: bool = True,
        slow_mo_ms: int = 250,
        confirm: ConfirmFn | None = None,
        dry_run: bool = False,
        on_step: Callable[[StepOutcome], None] | None = None,
    ) -> None:
        validate_recipe_invariants(recipe)
        self.recipe = recipe
        self.params = params
        self.headed = headed
        self.slow_mo_ms = slow_mo_ms
        self.confirm = confirm or default_confirm
        self.dry_run = dry_run
        self.on_step = on_step

        self.run_id = uuid4().hex
        self.budget = Budget()
        self.result = ReplayResult(
            run_id=self.run_id,
            recipe_id=recipe.id,
            task_name=recipe.task_name,
            steps_total=len(recipe.steps),
        )
        nav_targets = [
            s.aria_name or "" for s in recipe.steps if s.action == ActionType.NAV and s.aria_name
        ]
        self.known_hosts = known_domains(nav_targets)
        self._aborting = False
        self._abort_reason: AbortReason | None = None
        self._prev_sigint: Callable[..., object] | int | None = None

    def run(self) -> ReplayResult:
        settings = get_settings()
        log_event(self.run_id, "run.start", recipe_id=self.recipe.id, steps=len(self.recipe.steps))
        self._install_sigint()
        try:
            with sync_playwright() as pw:
                ctx, page = self._launch(pw)
                try:
                    self._drive_loop(page)
                finally:
                    self._teardown(ctx)
        except Exception as e:
            self.result.status = "error"
            self.result.abort_reason = self._abort_reason or AbortReason.UNKNOWN
            log_event(self.run_id, "run.error", error=type(e).__name__)
        finally:
            self._restore_sigint()
            self._finalise()
            log_path = settings.replays_dir() / f"{self.run_id}.json"
            # 0o600 — result file may carry eTLD+1s and redacted step intents.
            fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(self.result.model_dump_json(indent=2))
            self.result.log_path = str(log_path)
            log_event(
                self.run_id,
                "run.end",
                status=self.result.status,
                steps_done=self.result.steps_done,
                cost=self.result.cost_usd,
            )
        return self.result

    # ------------------------------------------------------------------
    # lifecycle helpers

    def _launch(self, pw: Playwright) -> tuple[BrowserContext, Page]:
        browser = pw.chromium.launch(headless=not self.headed, slow_mo=self.slow_mo_ms)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        ctx.on("page", lambda p: p.on("download", self._on_download))
        page = ctx.new_page()
        page.on("download", self._on_download)
        page.on("dialog", lambda d: d.dismiss())
        page.on("framenavigated", self._on_framenavigated)
        return ctx, page

    def _teardown(self, ctx: BrowserContext) -> None:
        try:
            ctx.browser.close() if ctx.browser else ctx.close()
        except Exception as e:
            log.debug("browser close raised: %s", e)

    def _install_sigint(self) -> None:
        def handler(_sig: int, _frame: object) -> None:
            log.warning("SIGINT received; aborting at end of current step")
            self._aborting = True
            self._abort_reason = AbortReason.USER

        self._prev_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, handler)

    def _restore_sigint(self) -> None:
        import contextlib

        if self._prev_sigint is not None:
            with contextlib.suppress(TypeError, ValueError):
                signal.signal(signal.SIGINT, self._prev_sigint)  # type: ignore[arg-type]

    def _on_download(self, download: Download) -> None:
        log_event(self.run_id, "download.cancelled", suggested_filename=download.suggested_filename)
        try:
            download.cancel()
        except Exception as e:
            log.debug("download cancel raised: %s", e)

    def _on_framenavigated(self, frame: object) -> None:
        # Ignore subframe navigation (iframes for ads, analytics, auth embeds);
        # only top-frame drift is a security signal for the replay loop.
        parent = getattr(frame, "parent_frame", None)
        if parent is not None:
            return
        url = getattr(frame, "url", None)
        if not url or url.startswith("about:"):
            return
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            return
        if not host:
            return
        if not is_allowed(url):
            log.warning("top-frame nav to denied domain: %s", host)
            self._aborting = True
            self._abort_reason = AbortReason.DOMAIN_DRIFT
            log_event(self.run_id, "drift.denied_domain", host=host)
            return

    # ------------------------------------------------------------------
    # the main loop

    def _drive_loop(self, page: Page) -> None:
        completed: list[StepOutcome] = []
        for step in self.recipe.steps:
            if self._aborting:
                break
            if self.budget.over():
                self._abort_reason = AbortReason.BUDGET
                break
            outcome = self._run_step(page, step, completed)
            completed.append(outcome)
            self.result.outcomes.append(outcome)
            self.result.steps_done += 1
            if self.on_step:
                try:
                    self.on_step(outcome)
                except Exception as e:
                    log.debug("on_step callback raised: %s", e)
            if outcome.status in {StepStatus.ERROR, StepStatus.ABORTED, StepStatus.BUDGET}:
                break

    def _run_step(
        self,
        page: Page,
        step: RecipeStep,
        completed: list[StepOutcome],
    ) -> StepOutcome:
        t0 = time.monotonic()
        intent = step.intent
        url = page.url if page else None
        needs, reason = must_confirm(
            step,
            current_url=url,
            recipe_known_domains=self.known_hosts,
            completed=completed,
        )
        if needs:
            detail = f"{step.action.value} {step.aria_name or ''}".strip()
            decision = self.confirm(step, reason, detail)
            log_event(
                self.run_id,
                "hitl.prompt",
                step=step.idx,
                reason=reason,
                decision=decision,
            )
            if decision != "approve":
                self._aborting = decision == "abort"
                if self._aborting:
                    self._abort_reason = AbortReason.USER
                return StepOutcome(
                    idx=step.idx,
                    intent=intent,
                    status=StepStatus.ABORTED,
                    ms=_ms(t0),
                    target_hint=step.aria_name,
                    error=reason,
                )

        try:
            value = render_template(step.value_template, self.params)
        except MissingParamError as e:
            self._abort_reason = AbortReason.PARAM_ERROR
            return StepOutcome(
                idx=step.idx,
                intent=intent,
                status=StepStatus.ERROR,
                ms=_ms(t0),
                target_hint=step.aria_name,
                error=f"missing_param:{e.args[0]}",
            )

        try:
            locator = ground(page, step)
        except GroundingError as e:
            log_event(
                self.run_id,
                "step.grounding_failed",
                step=step.idx,
                param_sha=hash_value(value) if value else None,
            )
            return StepOutcome(
                idx=step.idx,
                intent=intent,
                status=StepStatus.ERROR,
                ms=_ms(t0),
                target_hint=step.aria_name,
                error=str(e),
            )

        if self.dry_run:
            return StepOutcome(
                idx=step.idx,
                intent=intent,
                status=StepStatus.OK,
                ms=_ms(t0),
                target_hint=step.aria_name,
                url_etld1=etld1(url),
            )

        try:
            execute_action(ActionContext(page=page, locator=locator, value=value, step=step))
        except (ActionError, PWError) as e:
            # Do NOT log str(e): Playwright errors embed selectors + values
            # which can contain param data. Log only the exception class.
            err_class = type(e).__name__
            log_event(
                self.run_id,
                "step.action_failed",
                step=step.idx,
                action=step.action.value,
                error=err_class,
            )
            return StepOutcome(
                idx=step.idx,
                intent=intent,
                status=StepStatus.ERROR,
                ms=_ms(t0),
                target_hint=step.aria_name,
                error=f"{err_class} (details suppressed to prevent param leakage)",
            )

        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except PWError as e:
            log.debug("load state wait timed out: %s", e)

        ok = evaluate_success(page, step.success_check)
        status = StepStatus.OK if ok else StepStatus.SOFT_FAIL
        log_event(
            self.run_id,
            "step.done",
            step=step.idx,
            status=status.value,
            action=step.action.value,
            url_etld1=etld1(page.url),
        )
        return StepOutcome(
            idx=step.idx,
            intent=intent,
            status=status,
            ms=_ms(t0),
            target_hint=step.aria_name,
            url_etld1=etld1(page.url),
        )

    # ------------------------------------------------------------------

    def _finalise(self) -> None:
        self.result.finished_at = _now_iso()
        self.result.cost_usd = self.budget.used_usd
        self.result.llm_calls = self.budget.used_calls
        if self._abort_reason:
            self.result.status = "aborted"
            self.result.abort_reason = self._abort_reason
        elif any(o.status == StepStatus.ERROR for o in self.result.outcomes):
            self.result.status = "error"
        elif any(o.status != StepStatus.OK for o in self.result.outcomes):
            self.result.status = "partial"
        else:
            self.result.status = "ok"


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_recipe(recipe_id: str) -> Recipe:
    """Fetch a recipe row from the DB and validate it."""
    from understudy.db import session

    with session() as conn:
        row = conn.execute(
            "SELECT recipe_json FROM recipes WHERE id = ?",
            (recipe_id,),
        ).fetchone()
    if not row:
        raise FileNotFoundError(f"recipe not found: {recipe_id}")
    raw = row[0]
    try:
        return Recipe.model_validate_json(raw)
    except ValidationError as e:
        raise RecipeInvariantError(f"stored recipe is malformed: {e}") from e
