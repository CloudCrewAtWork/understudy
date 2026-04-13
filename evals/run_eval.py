"""Eval harness skeleton. Wired against pytest in the test suite; this script is for ad-hoc runs.

Usage:
    uv run python evals/run_eval.py            # runs every case in evals/cases/*.yaml
    uv run python evals/run_eval.py google_search_basic

Each run writes a JSONL row to evals/runs/<timestamp>/results.jsonl with:
  task, variant, pass, steps, tokens_in, tokens_out, cost_usd, wall_ms, error_class
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
CASES_DIR = ROOT / "cases"
RUNS_DIR = ROOT / "runs"


def load_cases(filter_name: str | None = None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for f in sorted(CASES_DIR.glob("*.yaml")):
        case = yaml.safe_load(f.read_text())
        case["__file"] = str(f)
        if filter_name and case.get("name") != filter_name:
            continue
        cases.append(case)
    return cases


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Stub. Real runner lands when replay engine ships.

    For now, we record the case shape so the eval table has structure to grow into.
    """
    return {
        "task": case["name"],
        "variant": "default",
        "pass": False,
        "steps": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "wall_ms": 0,
        "error_class": "not_implemented",
    }


def main(argv: list[str]) -> int:
    flt = argv[1] if len(argv) > 1 else None
    cases = load_cases(flt)
    if not cases:
        print(f"no cases matched filter={flt!r}", file=sys.stderr)
        return 1
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = RUNS_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "results.jsonl"
    t0 = time.monotonic()
    with out.open("w", encoding="utf-8") as f:
        for case in cases:
            row = run_case(case)
            f.write(json.dumps(row) + "\n")
    print(f"wrote {len(cases)} rows -> {out} ({(time.monotonic() - t0) * 1000:.0f} ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
