"""Eval harness runner.

Each case YAML in `evals/cases/*.yaml` names a recipe (as a JSON file on
disk — no DB round-trip, so the harness is self-contained) and a list of
fixture variants. For each variant the runner:

  1. Spins up the fixture HTTP server on an ephemeral loopback port.
  2. Builds the variant's target URL.
  3. Instantiates a Replayer with the recipe and `{url: <fixture>}` params.
  4. Runs headless to completion.
  5. Compares the extracted notes against `expect_extracts`.

Results land in `evals/runs/<timestamp>/` as:
  - `results.jsonl` — one row per (case, variant)
  - `results.md`    — human-readable pass-rate table
  - `latest` symlink (updated after each run) for README auto-inclusion

Usage:
    uv run python evals/run_eval.py                 # every case
    uv run python evals/run_eval.py repo_triage     # one case
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from understudy.replay import Replayer
from understudy.replay.batch import _load_notes
from understudy.types import Recipe

from .fixture_server import FIXTURES_DIR, FixtureServer

ROOT = Path(__file__).resolve().parent
CASES_DIR = ROOT / "cases"
RUNS_DIR = ROOT / "runs"
PROJECT_ROOT = ROOT.parent


@dataclass
class VariantResult:
    case: str
    variant: str
    passed: bool
    extracts_matched: int
    extracts_expected: int
    missing_fields: list[str]
    wrong_fields: dict[str, tuple[str, str]]
    wall_ms: int
    llm_calls: int
    cost_usd: float
    status: str
    error_class: str | None


def _load_recipe(recipe_path: Path) -> Recipe:
    return Recipe.model_validate_json(recipe_path.read_text(encoding="utf-8"))


def _compare(
    expected: dict[str, str], actual: dict[str, str],
) -> tuple[int, list[str], dict[str, tuple[str, str]]]:
    matched = 0
    missing: list[str] = []
    wrong: dict[str, tuple[str, str]] = {}
    for k, v in expected.items():
        if k not in actual:
            missing.append(k)
            continue
        if actual[k].strip() == v.strip():
            matched += 1
        else:
            wrong[k] = (v, actual[k])
    return matched, missing, wrong


def _run_variant(
    case_name: str, recipe: Recipe, variant: dict[str, Any], base_url: str,
) -> VariantResult:
    fixture = variant["fixture"]
    label = variant.get("label") or fixture
    url = f"{base_url}/{fixture}"
    expected = {str(k): str(v) for k, v in (variant.get("expect_extracts") or {}).items()}

    # Hand-seeded recipes carry an empty allowlist; patch in the fixture host
    # so the egress filter permits the loopback replay. We use "localhost"
    # (not "127.0.0.1") because url_host refuses IP literals.
    recipe_for_run = recipe.model_copy(update={"allowed_origins": ["localhost"]})

    replayer = Replayer(
        recipe_for_run,
        params={"url": url},
        headed=False,
        slow_mo_ms=0,
        hold_seconds=0.0,
    )

    t0 = time.monotonic()
    try:
        result = replayer.run()
    except Exception as e:
        return VariantResult(
            case=case_name, variant=label, passed=False,
            extracts_matched=0, extracts_expected=len(expected),
            missing_fields=list(expected), wrong_fields={},
            wall_ms=int((time.monotonic() - t0) * 1000),
            llm_calls=0, cost_usd=0.0, status="error",
            error_class=type(e).__name__,
        )

    actual = _load_notes(result.run_id)
    matched, missing, wrong = _compare(expected, actual)
    return VariantResult(
        case=case_name,
        variant=label,
        passed=(matched == len(expected)) and (result.status == "ok"),
        extracts_matched=matched,
        extracts_expected=len(expected),
        missing_fields=missing,
        wrong_fields=wrong,
        wall_ms=int((time.monotonic() - t0) * 1000),
        llm_calls=result.llm_calls,
        cost_usd=result.cost_usd,
        status=result.status,
        error_class=None,
    )


def load_cases(filter_name: str | None = None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for f in sorted(CASES_DIR.glob("*.yaml")):
        case = yaml.safe_load(f.read_text())
        case["__file"] = str(f)
        if filter_name and case.get("name") != filter_name:
            continue
        cases.append(case)
    return cases


def markdown_table(results: list[VariantResult]) -> str:
    by_case: dict[str, list[VariantResult]] = {}
    for r in results:
        by_case.setdefault(r.case, []).append(r)
    lines: list[str] = [
        "| Case | Variant | Pass | Extracts | Status | Wall (ms) |",
        "|---|---|:---:|:---:|---|---:|",
    ]
    for case_name, variants in by_case.items():
        for v in variants:
            mark = "✅" if v.passed else "❌"
            ex = f"{v.extracts_matched}/{v.extracts_expected}"
            lines.append(
                f"| `{case_name}` | `{v.variant}` | {mark} | {ex} | {v.status} | {v.wall_ms} |"
            )
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    pct = (passed / total * 100) if total else 0.0
    lines.append("")
    lines.append(f"**Overall: {passed}/{total} variants passed ({pct:.0f}%).**")
    return "\n".join(lines)


def _update_latest_symlink(run_dir: Path) -> None:
    latest = RUNS_DIR / "latest"
    with contextlib.suppress(Exception):
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(run_dir.name, target_is_directory=True)


def run_all(filter_name: str | None = None, out_dir: Path | None = None) -> list[VariantResult]:
    """Programmatic entrypoint. Returns the results; writes sidecars if out_dir set."""
    cases = load_cases(filter_name)
    results: list[VariantResult] = []
    with FixtureServer() as srv:
        for case in cases:
            recipe_path = PROJECT_ROOT / str(case["recipe_path"])
            recipe = _load_recipe(recipe_path)
            for variant in case.get("variants") or []:
                print(
                    f"  running {case['name']} · {variant.get('label', variant['fixture'])} ...",
                    file=sys.stderr,
                )
                results.append(_run_variant(case["name"], recipe, variant, srv.base_url))
    if out_dir is not None:
        _write_artifacts(out_dir, results)
    return results


def _write_artifacts(out_dir: Path, results: list[VariantResult]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "results.jsonl"
    with jsonl.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(
                json.dumps(
                    {
                        "case": r.case,
                        "variant": r.variant,
                        "passed": r.passed,
                        "extracts_matched": r.extracts_matched,
                        "extracts_expected": r.extracts_expected,
                        "missing_fields": r.missing_fields,
                        "wrong_fields": {
                            k: {"expected": v[0], "actual": v[1]}
                            for k, v in r.wrong_fields.items()
                        },
                        "wall_ms": r.wall_ms,
                        "llm_calls": r.llm_calls,
                        "cost_usd": r.cost_usd,
                        "status": r.status,
                        "error_class": r.error_class,
                    }
                )
                + "\n"
            )
    (out_dir / "results.md").write_text(markdown_table(results) + "\n", encoding="utf-8")
    _update_latest_symlink(out_dir)


def main(argv: list[str]) -> int:
    flt = argv[1] if len(argv) > 1 else None
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = RUNS_DIR / ts
    results = run_all(flt, out_dir=out_dir)
    if not results:
        print(f"no cases matched filter={flt!r}", file=sys.stderr)
        return 1
    print(markdown_table(results))
    print(f"\nwrote {len(results)} rows → {out_dir / 'results.jsonl'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))


# Re-export for tests that want to stand up the fixture server directly.
__all__ = ["FIXTURES_DIR", "FixtureServer", "markdown_table", "run_all"]
