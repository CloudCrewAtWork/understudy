import pytest

from understudy.replay.substitute import MissingParamError, render_template


def test_basic():
    assert render_template("hi {name}", {"name": "Anurag"}) == "hi Anurag"


def test_empty_template():
    assert render_template(None, {}) == ""
    assert render_template("", {}) == ""


def test_missing_param():
    with pytest.raises(MissingParamError):
        render_template("hi {name}", {})


def test_dunder_blocked():
    with pytest.raises(ValueError, match="nested access blocked"):
        render_template("{x.__class__}", {"x": "ok"})


def test_subscript_blocked():
    with pytest.raises(ValueError, match="nested access blocked"):
        render_template("{x[0]}", {"x": "hi"})


def test_multiple_substitutions():
    assert render_template("{a} and {b}", {"a": "1", "b": "2"}) == "1 and 2"


def test_unused_params_are_fine():
    assert render_template("hi {name}", {"name": "x", "extra": "y"}) == "hi x"
