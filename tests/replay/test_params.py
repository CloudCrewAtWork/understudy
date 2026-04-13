from pathlib import Path

import pytest

from understudy.replay.params import ParamError, validate_params
from understudy.types import ActionType, Recipe, RecipeParam, RecipeStep, TargetKind


def _recipe(*params: RecipeParam) -> Recipe:
    return Recipe(
        task_name="t",
        target_kind=TargetKind.BROWSER,
        source_trajectory_id="x",
        induced_by="test",
        description="d",
        params=list(params),
        steps=[RecipeStep(idx=1, intent="noop", action=ActionType.NOTE)],
    )


def test_string_passthrough():
    r = _recipe(RecipeParam(name="q", type="string", description=""))
    assert validate_params(r, {"q": "hello"})["q"] == "hello"


def test_size_cap():
    r = _recipe(RecipeParam(name="q", type="string", description=""))
    with pytest.raises(ParamError, match="exceeds"):
        validate_params(r, {"q": "x" * 5000})


def test_control_chars_stripped():
    r = _recipe(RecipeParam(name="q", type="string", description=""))
    out = validate_params(r, {"q": "a\x01b\x07c"})
    assert out["q"] == "abc"


def test_boolean_valid():
    r = _recipe(RecipeParam(name="b", type="boolean", description=""))
    assert validate_params(r, {"b": "TRUE"})["b"] == "true"


def test_boolean_invalid():
    r = _recipe(RecipeParam(name="b", type="boolean", description=""))
    with pytest.raises(ParamError):
        validate_params(r, {"b": "yes"})


def test_number_valid():
    r = _recipe(RecipeParam(name="n", type="number", description=""))
    assert validate_params(r, {"n": "42.5"})["n"] == "42.5"


def test_number_nan_rejected():
    r = _recipe(RecipeParam(name="n", type="number", description=""))
    with pytest.raises(ParamError):
        validate_params(r, {"n": "NaN"})


def test_email_valid():
    r = _recipe(RecipeParam(name="e", type="email", description=""))
    assert validate_params(r, {"e": "x@example.com"})["e"] == "x@example.com"


def test_email_invalid():
    r = _recipe(RecipeParam(name="e", type="email", description=""))
    with pytest.raises(ParamError):
        validate_params(r, {"e": "not-an-email"})


def test_url_scheme_rejected():
    r = _recipe(RecipeParam(name="u", type="url", description=""))
    with pytest.raises(ParamError):
        validate_params(r, {"u": "javascript:alert(1)"})


def test_url_denied_domain():
    r = _recipe(RecipeParam(name="u", type="url", description=""))
    with pytest.raises(ParamError):
        validate_params(r, {"u": "https://chase.com/"})


def test_unknown_param_rejected():
    r = _recipe(RecipeParam(name="q", type="string", description=""))
    with pytest.raises(ParamError, match="unknown"):
        validate_params(r, {"nope": "x"})


def test_missing_required():
    r = _recipe(RecipeParam(name="q", type="string", description=""))
    with pytest.raises(ParamError, match="missing required"):
        validate_params(r, {})


def test_optional_uses_example():
    r = _recipe(
        RecipeParam(
            name="q",
            type="string",
            description="",
            required=False,
            example="default",
        )
    )
    assert validate_params(r, {})["q"] == "default"


def test_csv_missing(tmp_path: Path):
    r = _recipe(RecipeParam(name="f", type="csv_path", description=""))
    with pytest.raises(ParamError, match="not found"):
        validate_params(r, {"f": str(tmp_path / "missing.csv")})


def test_csv_wrong_suffix(tmp_path: Path):
    r = _recipe(RecipeParam(name="f", type="csv_path", description=""))
    p = tmp_path / "data.txt"
    p.write_text("x")
    with pytest.raises(ParamError, match=r"\.csv"):
        validate_params(r, {"f": str(p)})
