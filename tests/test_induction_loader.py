"""Trajectory loader tests — specifically the `<id>.meta.json` sidecar.

The sidecar carries the capture-time origin allowlist. The loader must:
- populate `Trajectory.allowed_origins` when the sidecar is present and valid
- degrade gracefully when the sidecar is missing (legacy recordings)
- refuse to crash on a malformed sidecar (we warn and fall back to empty)
"""

from __future__ import annotations

import json
from pathlib import Path

from understudy.induction.induce import load_trajectory
from understudy.types import ActionType, TrajectoryStep


def _write_jsonl(path: Path, steps: list[TrajectoryStep]) -> None:
    path.write_text(
        "\n".join(s.model_dump_json() for s in steps) + "\n",
        encoding="utf-8",
    )


def test_loader_reads_sidecar_origins(tmp_path: Path) -> None:
    jsonl = tmp_path / "abc123.jsonl"
    _write_jsonl(
        jsonl,
        [TrajectoryStep(idx=1, action=ActionType.NAV, url="https://example.com/")],
    )
    sidecar = tmp_path / "abc123.meta.json"
    sidecar.write_text(
        json.dumps({"allowed_origins": ["example.com", "cdn.example.com"]}),
        encoding="utf-8",
    )

    traj = load_trajectory(jsonl)
    assert traj.allowed_origins == ["example.com", "cdn.example.com"]


def test_loader_handles_missing_sidecar(tmp_path: Path) -> None:
    jsonl = tmp_path / "legacy.jsonl"
    _write_jsonl(
        jsonl,
        [TrajectoryStep(idx=1, action=ActionType.NAV, url="https://example.com/")],
    )

    traj = load_trajectory(jsonl)
    assert traj.allowed_origins == []


def test_loader_handles_malformed_sidecar(tmp_path: Path) -> None:
    jsonl = tmp_path / "bad.jsonl"
    _write_jsonl(
        jsonl,
        [TrajectoryStep(idx=1, action=ActionType.NAV, url="https://example.com/")],
    )
    (tmp_path / "bad.meta.json").write_text("not-json{", encoding="utf-8")

    traj = load_trajectory(jsonl)
    assert traj.allowed_origins == []


def test_loader_filters_non_string_origins(tmp_path: Path) -> None:
    jsonl = tmp_path / "mixed.jsonl"
    _write_jsonl(
        jsonl,
        [TrajectoryStep(idx=1, action=ActionType.NAV, url="https://example.com/")],
    )
    (tmp_path / "mixed.meta.json").write_text(
        json.dumps({"allowed_origins": ["ok.com", 42, None, "also.com"]}),
        encoding="utf-8",
    )

    traj = load_trajectory(jsonl)
    assert traj.allowed_origins == ["ok.com", "also.com"]
