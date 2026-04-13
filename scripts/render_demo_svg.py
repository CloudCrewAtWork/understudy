"""Render a sample LiveRunUI frame to SVG for embedding in the README.

This is intentionally a canned sequence: it feeds the exact UI widget used in
production with a plausible sequence of outcomes and saves the rendered
terminal as an SVG. No real replay runs; no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from understudy.replay.result import (  # noqa: E402
    ReplayResult,
    StepOutcome,
    StepStatus,
)
from understudy.replay.ui import LiveRunUI, render_summary  # noqa: E402
from understudy.types import ActionType, RecipeStep  # noqa: E402

SAMPLE_OUTCOMES: list[StepOutcome] = [
    StepOutcome(
        idx=1,
        intent="open duckduckgo homepage",
        status=StepStatus.OK,
        ms=412,
        target_hint=None,
        url_etld1="duckduckgo.com",
    ),
    StepOutcome(
        idx=2,
        intent="focus the search box",
        status=StepStatus.OK,
        ms=89,
        target_hint="Search the web",
        url_etld1="duckduckgo.com",
    ),
    StepOutcome(
        idx=3,
        intent="type {query}",
        status=StepStatus.OK,
        ms=156,
        target_hint="Search the web",
        url_etld1="duckduckgo.com",
    ),
    StepOutcome(
        idx=4,
        intent="submit the search",
        status=StepStatus.OK,
        ms=634,
        target_hint="Search",
        url_etld1="duckduckgo.com",
    ),
    StepOutcome(
        idx=5,
        intent="wait for results to render",
        status=StepStatus.OK,
        ms=812,
        target_hint=None,
        url_etld1="duckduckgo.com",
    ),
]

_CURRENT = RecipeStep(
    idx=6,
    intent="read the first result title",
    action=ActionType.CLICK,
    aria_role="link",
    aria_name="Top result",
)


def main() -> None:
    console = Console(record=True, width=92, force_terminal=True, color_system="truecolor")
    ui = LiveRunUI(console, "duckduckgo-search", total=6)
    for o in SAMPLE_OUTCOMES:
        ui.finish_step(o)
    ui.start_step(_CURRENT)
    console.print(ui.render())

    result = ReplayResult(
        run_id="demo00000000000000000000000000000",
        recipe_id="ddg_search",
        task_name="duckduckgo-search",
        started_at="2026-04-13T08:40:00Z",
        finished_at="2026-04-13T08:40:03Z",
        status="ok",
        abort_reason=None,
        steps_total=6,
        steps_done=6,
        cost_usd=0.0,
        llm_calls=0,
        outcomes=[
            *SAMPLE_OUTCOMES,
            StepOutcome(
                idx=6,
                intent="read the first result title",
                status=StepStatus.OK,
                ms=203,
                target_hint="Top result",
                url_etld1="duckduckgo.com",
            ),
        ],
        log_path="~/.understudy/replays/demo.json",
    )
    render_summary(console, result)

    out = ROOT / "docs" / "assets" / "replay-demo.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    console.save_svg(str(out), title="understudy replay ddg_search --param query='claude agents'")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
