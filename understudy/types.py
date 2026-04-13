"""Pydantic models for trajectories and recipes. The wire format of the project."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _uuid() -> str:
    return uuid4().hex


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class TargetKind(StrEnum):
    BROWSER = "browser"
    MACOS = "macos"


class ActionType(StrEnum):
    NAV = "nav"
    CLICK = "click"
    DBLCLICK = "dblclick"
    TYPE = "type"
    KEY = "key"
    SCROLL = "scroll"
    WAIT = "wait"
    SELECT = "select"
    UPLOAD = "upload"
    NOTE = "note"


class TrajectoryStep(BaseModel):
    """One observed step. Coordinates and selectors are best-effort.

    aria_ref is the stable anchor: a hash of role+name+ancestry path.
    Replay re-grounds against it rather than trusting raw selectors.
    """

    model_config = ConfigDict(extra="forbid")

    idx: int
    ts: str = Field(default_factory=_now)
    action: ActionType
    url: str | None = None
    selector: str | None = None
    aria_ref: str | None = None
    aria_role: str | None = None
    aria_name: str | None = None
    text: str | None = None
    key: str | None = None
    coords: tuple[int, int] | None = None
    screenshot_path: str | None = None
    aria_snapshot_hash: str | None = None
    notes: str | None = None
    redacted: bool = False


class Trajectory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_uuid)
    task_name: str
    target_kind: TargetKind = TargetKind.BROWSER
    started_at: str = Field(default_factory=_now)
    finished_at: str | None = None
    success: bool | None = None
    notes: str | None = None
    steps: list[TrajectoryStep] = Field(default_factory=list)


class RecipeParam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["string", "number", "boolean", "csv_path", "url", "email"] = "string"
    description: str
    example: str | None = None
    required: bool = True


class RecipeStep(BaseModel):
    """One step of a parameterized recipe.

    `intent` is the natural-language description of the action's goal.
    The replayer plans against `intent` + current page state, not against
    a frozen selector. `grounding_hint` is a soft anchor (aria_ref/role+name).
    """

    model_config = ConfigDict(extra="forbid")

    idx: int
    intent: str
    action: ActionType
    grounding_hint: str | None = None
    aria_role: str | None = None
    aria_name: str | None = None
    value_template: str | None = None
    success_check: str | None = None
    requires_confirmation: bool = False


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_uuid)
    task_name: str
    target_kind: TargetKind
    source_trajectory_id: str
    induced_by: str
    created_at: str = Field(default_factory=_now)
    description: str
    params: list[RecipeParam] = Field(default_factory=list)
    steps: list[RecipeStep]
    safety_notes: str | None = None
