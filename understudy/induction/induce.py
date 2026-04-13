"""Trace → parameterized Recipe via Claude.

Cost shape (Sonnet 4.5, April 2026 pricing assumption):
- Input: ~3k tokens system (CACHED) + ~2k tokens trace.
- Output: ~1.5k tokens recipe.
- ~$0.01-0.03 per induction with prompt caching on hits.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path

from anthropic import Anthropic
from anthropic.types import TextBlock

from understudy.config import get_settings
from understudy.db import insert_recipe, session
from understudy.types import Recipe, TargetKind, Trajectory, TrajectoryStep

from .prompts import SYSTEM, VERSION, build_user_message

log = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 4096
MAX_RESPONSE_BYTES = 256_000  # cap on returned JSON to bound parsing cost


def load_trajectory(path: Path) -> Trajectory:
    """Reconstitute a Trajectory from its JSONL file. Trajectory metadata is in DB."""
    steps: list[TrajectoryStep] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            steps.append(TrajectoryStep.model_validate_json(stripped))

    # The trajectory's real task_name lives in the DB index, not the filename.
    from understudy.db import session

    task_name = path.stem
    try:
        with session() as conn:
            row = conn.execute(
                "SELECT task_name FROM trajectories WHERE id = ?",
                (path.stem,),
            ).fetchone()
            if row and row[0]:
                task_name = row[0]
    except Exception as e:
        log.debug("could not look up task_name from DB: %s", e)

    return Trajectory(
        id=path.stem,
        task_name=task_name,
        target_kind=TargetKind.BROWSER,
        steps=steps,
    )


def induce_recipe(trajectory: Trajectory, *, persist: bool = True) -> Recipe:
    s = get_settings()
    api_key = s.anthropic_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; cannot induce recipe.")

    client = Anthropic(api_key=api_key)

    steps_json = json.dumps(
        [step.model_dump(mode="json") for step in trajectory.steps],
        indent=2,
    )
    user_msg = build_user_message(
        task_name=trajectory.task_name,
        target_kind=trajectory.target_kind.value,
        trajectory_id=trajectory.id,
        steps_json=steps_json,
    )

    log.info(
        "inducing recipe (model=%s, prompt=%s, %d steps)",
        s.induction_model,
        VERSION,
        len(trajectory.steps),
    )

    msg = client.messages.create(
        model=s.induction_model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = _extract_text(msg.content)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError(f"induction response too large: {len(raw)} bytes")
    payload = _parse_json(raw)
    payload.setdefault("source_trajectory_id", trajectory.id)
    payload.setdefault("induced_by", s.induction_model)
    payload.setdefault("target_kind", trajectory.target_kind.value)
    recipe = Recipe.model_validate(payload)

    if persist:
        with session() as conn:
            insert_recipe(conn, recipe)
    return recipe


def _extract_text(content: Sequence[object]) -> str:
    parts: list[str] = []
    for block in content:
        if isinstance(block, TextBlock):
            parts.append(block.text)
    return "".join(parts).strip()


def _parse_json(raw: str) -> dict[str, object]:
    """Tolerate accidental code fences but otherwise demand strict JSON."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[:-3]
    s = s.strip()
    return json.loads(s)
