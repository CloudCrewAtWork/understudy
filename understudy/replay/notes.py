"""Per-run note persistence.

A `note` recipe step with a grounded target extracts the element's
`inner_text` (see `replay/actions.py:_do_note`). That extracted text lands
here as a one-line JSON record in `<replays_dir>/<run_id>.notes.jsonl` —
the batch-replay loop reads these to assemble a CSV of results (e.g., a
table of GitHub-repo metadata triaged across a list of repos).

One line per note step with `extracted != None`. Schema:
    {
      "run_id": str,
      "step_idx": int,
      "intent": str,                   # plain-English step description
      "value_template": str | None,    # the recipe's field name hint
      "extracted": str,                # the actual text from the page
      "url_etld1": str | None,
    }
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterable
from pathlib import Path

from understudy.config import get_settings
from understudy.types import ActionType, RecipeStep

from .result import ReplayResult


def write_notes(
    result: ReplayResult,
    recipe_steps: Iterable[RecipeStep],
) -> Path | None:
    """Write one line per extracted note. Returns the path written, or None
    if the run produced no extracts.
    """
    idx_to_step = {s.idx: s for s in recipe_steps if s.action == ActionType.NOTE}
    path = get_settings().replays_dir() / f"{result.run_id}.notes.jsonl"
    rows: list[dict[str, object]] = []
    for outcome in result.outcomes:
        if outcome.extracted is None:
            continue
        step = idx_to_step.get(outcome.idx)
        rows.append(
            {
                "run_id": result.run_id,
                "step_idx": outcome.idx,
                "intent": outcome.intent,
                "value_template": step.value_template if step else None,
                "extracted": outcome.extracted,
                "url_etld1": outcome.url_etld1,
            }
        )
    if not rows:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with contextlib.suppress(OSError):
        path.chmod(0o600)
    return path
