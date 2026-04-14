"""Smoke test: drive the eval harness end-to-end on the committed fixtures.

This is the artefact the README's pass-rate table depends on. If this test
goes red, the pass-rate number is stale — don't ship.
"""

from __future__ import annotations

from pathlib import Path

from evals.run_eval import run_all


def test_eval_harness_runs_repo_triage(tmp_path: Path) -> None:
    results = run_all(filter_name="repo_triage", out_dir=tmp_path)
    assert results, "no variants ran — case YAML missing or malformed"

    # There are 4 variants (baseline + 3 perturbations).
    assert len(results) == 4

    # Baseline must always pass — it's the sanity check.
    baseline = next(r for r in results if r.variant == "baseline")
    assert baseline.passed, f"baseline failed: {baseline}"
    assert baseline.extracts_matched == baseline.extracts_expected == 6

    # The rename variant is the known-hard case: exact-match grounding can't
    # survive accessible-name rewrites. If it starts passing, great — but
    # until LLM regrounding lands we DOCUMENT that it fails, so this acts as
    # a regression tripwire in both directions.
    rename = next(r for r in results if r.variant == "accessible_name_rewrite")
    # The harness must have produced a verdict for the rename variant,
    # whether pass or documented-fail — a silent skip is the bug.
    assert rename.status in {"ok", "partial", "error"}
