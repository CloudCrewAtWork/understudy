"""Request / response schemas for the UI API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from understudy.types import Recipe, RecipeStep


class RecipeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_name: str
    description: str
    created_at: str
    edited_at: str | None = None
    step_count: int
    param_count: int


class StepPatch(BaseModel):
    """Fields a PATCH may update on a RecipeStep.

    The API never accepts structural fields (idx, action) via raw PATCH —
    those must go through resynthesize, which re-validates invariants.
    """

    model_config = ConfigDict(extra="forbid")

    intent: str | None = Field(default=None, max_length=2000)
    value_template: str | None = Field(default=None, max_length=500)
    requires_confirmation: bool | None = None
    success_check: str | None = Field(default=None, max_length=500)


class ResynthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_intent: str = Field(min_length=1, max_length=2000)
    apply: bool = False


class ResynthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_step: RecipeStep
    new_step: RecipeStep
    reasoning: str | None = None
    applied: bool
    recipe: Recipe | None = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str
    detail: str | None = None
