import json

from understudy.types import (
    ActionType,
    Recipe,
    RecipeParam,
    RecipeStep,
    TargetKind,
    Trajectory,
    TrajectoryStep,
)


def test_trajectory_roundtrip():
    t = Trajectory(task_name="login")
    t.steps.append(TrajectoryStep(idx=1, action=ActionType.NAV, url="https://example.com"))
    raw = t.model_dump_json()
    again = Trajectory.model_validate_json(raw)
    assert again.task_name == "login"
    assert again.steps[0].url == "https://example.com"
    assert again.steps[0].action is ActionType.NAV


def test_step_extra_field_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TrajectoryStep.model_validate({"idx": 1, "action": "click", "rogue_field": True})


def test_recipe_minimal():
    r = Recipe(
        task_name="t",
        target_kind=TargetKind.BROWSER,
        source_trajectory_id="abc",
        induced_by="claude-sonnet-4-5",
        description="d",
        params=[RecipeParam(name="email", type="email", description="user email")],
        steps=[RecipeStep(idx=1, intent="open page", action=ActionType.NAV)],
    )
    payload = json.loads(r.model_dump_json())
    assert payload["params"][0]["name"] == "email"
    assert payload["steps"][0]["intent"] == "open page"


def test_trajectory_allowed_origins_default_empty():
    t = Trajectory(task_name="x")
    assert t.allowed_origins == []


def test_trajectory_allowed_origins_roundtrip():
    t = Trajectory(
        task_name="x",
        allowed_origins=["duckduckgo.com", "cdn.duckduckgo.com"],
    )
    raw = t.model_dump_json()
    again = Trajectory.model_validate_json(raw)
    assert again.allowed_origins == ["duckduckgo.com", "cdn.duckduckgo.com"]


def test_recipe_allowed_origins_default_empty():
    r = Recipe(
        task_name="t",
        target_kind=TargetKind.BROWSER,
        source_trajectory_id="abc",
        induced_by="claude-sonnet-4-5",
        description="d",
        steps=[RecipeStep(idx=1, intent="open", action=ActionType.NAV)],
    )
    assert r.allowed_origins == []


def test_recipe_allowed_origins_persists():
    r = Recipe(
        task_name="t",
        target_kind=TargetKind.BROWSER,
        source_trajectory_id="abc",
        induced_by="claude-sonnet-4-5",
        description="d",
        steps=[RecipeStep(idx=1, intent="open", action=ActionType.NAV)],
        allowed_origins=["duckduckgo.com"],
    )
    payload = json.loads(r.model_dump_json())
    assert payload["allowed_origins"] == ["duckduckgo.com"]
