"""Batch replay: one recipe, many parameter rows.

The hero v0.3 demo is "triage N GitHub repos with a single recorded
recipe." A user hands us a CSV of parameter values (one row per iteration)
and we replay the recipe once per row, collecting extracted notes into a
CSV at the end.

The Python API is the source of truth (`run_batch`); the CLI wrapper
(`understudy replay --csv ...`) is a thin adapter. Eval harness,
notebooks, and any future scheduler all consume the API directly so there
is one code path.
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from understudy.config import get_settings

from .engine import ConfirmFn, Replayer, load_recipe
from .result import ReplayResult

log = logging.getLogger(__name__)


@dataclass
class BatchRow:
    """One iteration's inputs + outputs."""

    params: dict[str, str]
    result: ReplayResult
    extracts: dict[str, str]  # value_template → extracted text, flattened


def _load_notes(run_id: str) -> dict[str, str]:
    """Read `<run_id>.notes.jsonl` into a {value_template|intent → extracted} dict.

    Keyed on `value_template` when present (recipe author's structured field
    name) else `intent` (natural-language fallback). One row per note step.
    """
    path = get_settings().replays_dir() / f"{run_id}.notes.jsonl"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = str(
                row.get("value_template")
                or row.get("intent")
                or f"step_{row.get('step_idx')}"
            )
            out[key] = str(row.get("extracted", ""))
    return out


def run_batch(
    recipe_id: str,
    rows: Iterable[dict[str, str]],
    *,
    headed: bool = False,
    slow_mo_ms: int = 0,
    confirm: ConfirmFn | None = None,
) -> Iterator[BatchRow]:
    """Replay `recipe_id` once per row, yielding BatchRow per iteration.

    Iterator (not list) so large CSVs stream — caller decides whether to
    `list(...)` or write incrementally. Each iteration is its own Replayer
    instance; browser is torn down + relaunched between rows. This is the
    simplest correct semantics; concurrency is a v0.4 concern.
    """
    recipe = load_recipe(recipe_id)
    for params in rows:
        replayer = Replayer(
            recipe,
            params=dict(params),
            headed=headed,
            slow_mo_ms=slow_mo_ms,
            confirm=confirm,
        )
        result = replayer.run()
        extracts = _load_notes(result.run_id)
        yield BatchRow(params=dict(params), result=result, extracts=extracts)


def run_csv(
    recipe_id: str,
    csv_path: Path,
    out_path: Path | None = None,
    *,
    headed: bool = False,
    slow_mo_ms: int = 0,
) -> Path:
    """Batch-replay a recipe across every row of a CSV, writing results.

    Output CSV columns = input columns + every distinct extract key +
    `status`, `steps_done`, `wall_ms`, `run_id`. One row per input row.
    Returns the written path.
    """
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        input_rows = list(reader)
        input_cols = reader.fieldnames or []

    if not input_rows:
        raise ValueError(f"CSV has no rows: {csv_path}")

    out_path = out_path or csv_path.with_name(
        f"{csv_path.stem}-results-{uuid4().hex[:8]}.csv"
    )

    batch_results: list[BatchRow] = []
    for br in run_batch(recipe_id, input_rows, headed=headed, slow_mo_ms=slow_mo_ms):
        batch_results.append(br)
        log.info(
            "batch row %s → %s (%d/%d steps, %d ms)",
            br.params,
            br.result.status,
            br.result.steps_done,
            br.result.steps_total,
            int(sum(o.ms for o in br.result.outcomes)),
        )

    # Union of every extract key across rows keeps the output CSV rectangular
    # even if some rows failed to produce all fields.
    extract_keys: list[str] = sorted({k for br in batch_results for k in br.extracts})
    out_cols = list(input_cols) + extract_keys + ["status", "steps_done", "wall_ms", "run_id"]

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_cols)
        writer.writeheader()
        for br in batch_results:
            row: dict[str, str] = {**br.params}
            for k in extract_keys:
                row[k] = br.extracts.get(k, "")
            row["status"] = br.result.status
            row["steps_done"] = str(br.result.steps_done)
            row["wall_ms"] = str(sum(o.ms for o in br.result.outcomes))
            row["run_id"] = br.result.run_id
            writer.writerow(row)
    return out_path
