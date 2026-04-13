"""Rich-powered live UI for `understudy replay`.

The user sees: a header with the recipe name, a top pane that tracks the
currently-running step ("▸ step 3/7 'click the Billing tab'"), and a growing
log of completed steps below. On failure we print a structured block. On
HITL prompts we render a 3-line context + 10-second countdown.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from understudy.types import RecipeStep

from .result import StepOutcome, StepStatus

Decision = Literal["approve", "deny", "abort"]

_STATUS_GLYPH: dict[StepStatus, tuple[str, str]] = {
    StepStatus.OK: ("✓", "green"),
    StepStatus.SOFT_FAIL: ("~", "yellow"),
    StepStatus.ERROR: ("✗", "red"),
    StepStatus.ABORTED: ("⏸", "magenta"),
    StepStatus.BUDGET: ("$", "red"),
}


class LiveRunUI:
    """Renders the running replay. Call `on_step` after each step completes."""

    def __init__(self, console: Console, task_name: str, total: int) -> None:
        self.console = console
        self.task_name = task_name
        self.total = total
        self._outcomes: list[StepOutcome] = []
        self._current: RecipeStep | None = None
        self._current_started: float = 0.0

    def render(self) -> Group:
        header = Panel(
            Align.left(
                Text.from_markup(
                    f"[bold cyan]understudy replay[/bold cyan]  {self.task_name}  "
                    f"[dim]({len(self._outcomes)}/{self.total})[/dim]"
                )
            ),
            border_style="cyan",
        )
        cur_panel = self._render_current()
        log = self._render_log()
        return Group(header, cur_panel, log)

    def _render_current(self) -> Panel:
        if self._current is None:
            return Panel(Text("idle", style="dim"), border_style="grey30")
        elapsed = time.monotonic() - self._current_started
        intent = Text.from_markup(
            f"[bold]▸ step {self._current.idx}[/bold]  {self._current.intent}"
        )
        sub = Text.from_markup(f"  [dim]elapsed {elapsed:4.1f}s[/dim]")
        spinner = Spinner("dots", text="thinking…", style="cyan")
        return Panel(
            Group(intent, sub, spinner),
            border_style="cyan",
            title="current",
            title_align="left",
        )

    def _render_log(self) -> Panel:
        if not self._outcomes:
            return Panel(Text("no steps yet", style="dim"), border_style="grey30")
        table = Table.grid(padding=(0, 1))
        table.add_column(width=2)
        table.add_column(width=4)
        table.add_column()
        table.add_column(justify="right", width=8)
        for o in self._outcomes[-12:]:
            glyph, colour = _STATUS_GLYPH.get(o.status, ("?", "white"))
            table.add_row(
                Text(glyph, style=colour),
                Text(str(o.idx), style="dim"),
                Text(o.intent[:80]),
                Text(f"{o.ms}ms", style="dim"),
            )
        return Panel(table, border_style="grey30", title="log", title_align="left")

    # ---------- public API ----------

    def start_step(self, step: RecipeStep) -> None:
        self._current = step
        self._current_started = time.monotonic()

    def finish_step(self, outcome: StepOutcome) -> None:
        self._outcomes.append(outcome)
        self._current = None


def build_confirm_fn(console: Console, countdown_s: int = 10) -> Callable[..., Decision]:
    """Factory returning a ConfirmFn with a 10s auto-deny countdown."""

    import sys

    def confirm(step: RecipeStep, reason: str, detail: str) -> Decision:
        # In non-interactive contexts (CI, pipes), auto-deny immediately
        # — blocking 10s per prompt is worse than just refusing.
        if not sys.stdin.isatty():
            return "deny"
        console.print()
        console.print(
            Panel(
                Group(
                    Text.from_markup(f"[bold yellow]⏸  CONFIRM[/bold yellow]  {reason}"),
                    Text.from_markup(f"  intent : {step.intent}"),
                    Text.from_markup(f"  detail : {detail}"),
                    Text.from_markup(
                        f"  [dim]type [bold]y[/bold] to approve, "
                        f"[bold]a[/bold] to abort, anything else denies "
                        f"(auto-deny in {countdown_s}s)[/dim]"
                    ),
                ),
                border_style="yellow",
            )
        )
        # Non-Windows only: select() on stdin for the countdown.
        try:
            import select

            ready, _, _ = select.select([sys.stdin], [], [], countdown_s)
        except (OSError, ValueError):
            ready = []
        if not ready:
            console.print("[red]auto-denied (timeout)[/red]")
            return "deny"
        line = sys.stdin.readline().strip().lower()
        # Safer default: bare Enter DENIES. Must explicitly type y/yes.
        if line in {"y", "yes"}:
            return "approve"
        if line in {"a", "abort"}:
            return "abort"
        return "deny"

    return confirm


def render_failure(console: Console, outcome: StepOutcome, tried: str = "") -> None:
    body = Group(
        Text.from_markup(f"[bold red]✗ step {outcome.idx}[/bold red]  {outcome.intent}"),
        Text.from_markup(f"  [dim]target  :[/dim] {outcome.target_hint or '<none>'}"),
        Text.from_markup(f"  [dim]error   :[/dim] {outcome.error or '<unknown>'}"),
        Text.from_markup(
            f"  [dim]hint    :[/dim] run with [cyan]--dry-run[/cyan] "
            f"or edit the recipe: [cyan]understudy recipes show {outcome.idx}[/cyan]"
        ),
    )
    console.print(Panel(body, border_style="red"))


def render_summary(console: Console, result) -> None:  # result: ReplayResult
    status_colour = {"ok": "green", "partial": "yellow", "aborted": "magenta", "error": "red"}
    colour = status_colour.get(result.status, "white")
    lines = Group(
        Text.from_markup(
            f"[bold {colour}]{result.status.upper()}[/bold {colour}]  "
            f"{result.task_name}  "
            f"{result.steps_done}/{result.steps_total} steps  "
            f"${result.cost_usd:.3f}"
        ),
        Text.from_markup(
            f"  llm calls: {result.llm_calls}   abort reason: "
            f"{result.abort_reason.value if result.abort_reason else '—'}"
        ),
        Text.from_markup(f"  trace: [cyan]{result.log_path}[/cyan]"),
    )
    console.print(Panel(lines, border_style=colour, title="replay complete", title_align="left"))


def run_with_live_ui(
    console: Console,
    replayer,  # Replayer
    steps: list[RecipeStep],
) -> None:
    """Attach a LiveRunUI to the replayer via on_step callback."""
    ui = LiveRunUI(console, replayer.recipe.task_name, len(steps))
    with Live(ui.render(), console=console, refresh_per_second=6) as live:

        def on_step(outcome: StepOutcome) -> None:
            ui.finish_step(outcome)
            live.update(ui.render())

        # Monkey-patch start_step into the replayer by intercepting before/after.
        # Simpler: we expose on_step only; start is done implicitly on enter.
        replayer.on_step = on_step
        replayer.run()
        live.update(ui.render())
