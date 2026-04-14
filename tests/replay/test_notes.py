"""Tests for `replay/notes.py` and `replay/batch._load_notes`.

Both modules take the replays directory via `get_settings().replays_dir()`,
so the tests patch the module-local reference (not `understudy.config`
itself) — otherwise the already-imported name stays bound to the real
settings object and the tests write to the real data dir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from understudy.replay.notes import write_notes
from understudy.replay.result import ReplayResult, StepOutcome, StepStatus
from understudy.types import ActionType, RecipeStep


class _FakeSettings:
    def __init__(self, d: Path) -> None:
        self._d = d

    def replays_dir(self) -> Path:
        return self._d


def _result(run_id: str, outcomes: list[StepOutcome]) -> ReplayResult:
    return ReplayResult(
        run_id=run_id,
        recipe_id="r",
        task_name="t",
        outcomes=outcomes,
        steps_total=len(outcomes),
    )


def _step(idx: int, *, action: ActionType = ActionType.NOTE, vt: str | None = None) -> RecipeStep:
    return RecipeStep(idx=idx, intent=f"step {idx}", action=action, value_template=vt)


def test_write_notes_skips_when_no_extracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "understudy.replay.notes.get_settings", lambda: _FakeSettings(tmp_path)
    )
    result = _result(
        "run1",
        [StepOutcome(idx=1, intent="nothing", status=StepStatus.OK, ms=10)],
    )
    path = write_notes(result, [_step(1, action=ActionType.CLICK)])
    assert path is None
    assert not (tmp_path / "run1.notes.jsonl").exists()


def test_write_notes_emits_jsonl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "understudy.replay.notes.get_settings", lambda: _FakeSettings(tmp_path)
    )
    result = _result(
        "run2",
        [
            StepOutcome(
                idx=1, intent="get stars", status=StepStatus.OK, ms=20,
                extracted="4.2k", url_etld1="github.com",
            ),
            StepOutcome(
                idx=2, intent="get license", status=StepStatus.OK, ms=20,
                extracted="MIT", url_etld1="github.com",
            ),
        ],
    )
    steps = [_step(1, vt="stars"), _step(2, vt="license")]
    path = write_notes(result, steps)
    assert path is not None and path.exists()
    assert path.parent == tmp_path
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["value_template"] == "stars"
    assert rows[0]["extracted"] == "4.2k"
    assert rows[1]["value_template"] == "license"
    assert rows[1]["extracted"] == "MIT"


def test_write_notes_skips_outcomes_without_extracted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "understudy.replay.notes.get_settings", lambda: _FakeSettings(tmp_path)
    )
    result = _result(
        "run3",
        [
            StepOutcome(idx=1, intent="click", status=StepStatus.OK, ms=10),
            StepOutcome(idx=2, intent="note", status=StepStatus.OK, ms=10, extracted="data"),
        ],
    )
    steps = [_step(1, action=ActionType.CLICK), _step(2, vt="x")]
    path = write_notes(result, steps)
    assert path is not None
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["step_idx"] == 2


def test_batch_load_notes_keyed_on_value_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`run_csv` aggregates across rows via `_load_notes`; verify its key logic."""
    from understudy.replay.batch import _load_notes

    monkeypatch.setattr(
        "understudy.replay.batch.get_settings", lambda: _FakeSettings(tmp_path)
    )
    path = tmp_path / "abc.notes.jsonl"
    path.write_text(
        json.dumps({"step_idx": 1, "value_template": "stars", "extracted": "4200"})
        + "\n"
        + json.dumps({"step_idx": 2, "intent": "license", "extracted": "MIT"})
        + "\n",
        encoding="utf-8",
    )
    result = _load_notes("abc")
    assert result["stars"] == "4200"
    assert result["license"] == "MIT"


def test_batch_load_notes_missing_file_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from understudy.replay.batch import _load_notes

    monkeypatch.setattr(
        "understudy.replay.batch.get_settings", lambda: _FakeSettings(tmp_path)
    )
    assert _load_notes("no-such-run") == {}
