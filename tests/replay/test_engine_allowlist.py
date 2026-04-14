"""Replayer's egress-allowlist construction (unit-level, no Playwright)."""

from __future__ import annotations

from understudy.replay.engine import Replayer
from understudy.types import ActionType, Recipe, RecipeStep, TargetKind


def _recipe(**kwargs) -> Recipe:
    base = {
        "task_name": "t",
        "target_kind": TargetKind.BROWSER,
        "source_trajectory_id": "abc",
        "induced_by": "claude-sonnet-4-5",
        "description": "d",
        "steps": [
            RecipeStep(
                idx=1,
                intent="go",
                action=ActionType.NAV,
                aria_name="https://example.com/",
            )
        ],
    }
    base.update(kwargs)
    return Recipe(**base)


def test_allowlist_uses_capture_origins_when_present():
    r = _recipe(allowed_origins=["example.com", "cdn.example.com"])
    rp = Replayer(r, params={})
    assert rp.egress_allowlist == frozenset({"example.com", "cdn.example.com"})
    assert rp._allowlist_source == "capture"


def test_allowlist_falls_back_to_nav_hosts_for_legacy_recipe():
    r = _recipe()  # no allowed_origins
    rp = Replayer(r, params={})
    # known_domains extracts hosts from nav URL in aria_name
    assert "example.com" in rp.egress_allowlist
    assert rp._allowlist_source == "nav-fallback"


def test_empty_allowlist_when_no_origins_and_no_nav_urls():
    r = _recipe(
        steps=[RecipeStep(idx=1, intent="click", action=ActionType.CLICK)]
    )
    rp = Replayer(r, params={})
    assert rp.egress_allowlist == frozenset()
    assert rp._allowlist_source == "nav-fallback"
