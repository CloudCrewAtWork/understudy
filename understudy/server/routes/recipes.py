"""Recipe CRUD + resynth endpoints.

Every mutating path re-validates recipe invariants — edits cannot introduce
a denied-domain nav or overflow the step cap, even if Claude re-synthesises
something unsafe.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException

from understudy.db import session
from understudy.replay import RecipeInvariantError, validate_recipe_invariants
from understudy.server.resynth import resynthesise_step
from understudy.server.schemas import RecipeSummary, ResynthRequest, ResynthResponse, StepPatch
from understudy.types import Recipe

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["recipes"])


def _load_recipe(recipe_id: str) -> Recipe:
    with session() as conn:
        row = conn.execute(
            "SELECT recipe_json FROM recipes WHERE id = ?",
            (recipe_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"recipe not found: {recipe_id}")
    try:
        return Recipe.model_validate_json(row[0])
    except Exception as e:
        log.error("stored recipe %s is malformed: %s", recipe_id, e)
        raise HTTPException(status_code=500, detail="stored recipe is malformed") from e


def _save_recipe(recipe: Recipe) -> None:
    try:
        validate_recipe_invariants(recipe)
    except RecipeInvariantError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    with session() as conn:
        conn.execute(
            "UPDATE recipes SET recipe_json = ?, "
            "edited_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE id = ?",
            (recipe.model_dump_json(), recipe.id),
        )


@router.get("/recipes", response_model=list[RecipeSummary])
def list_recipes() -> list[RecipeSummary]:
    with session() as conn:
        rows = conn.execute(
            "SELECT id, task_name, created_at, edited_at, recipe_json "
            "FROM recipes ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    out: list[RecipeSummary] = []
    for row in rows:
        try:
            blob = json.loads(row[4])
        except json.JSONDecodeError:
            continue
        out.append(
            RecipeSummary(
                id=row[0],
                task_name=row[1],
                description=str(blob.get("description", "")),
                created_at=row[2],
                edited_at=row[3],
                step_count=len(blob.get("steps", [])),
                param_count=len(blob.get("params", [])),
            )
        )
    return out


@router.get("/recipes/{recipe_id}", response_model=Recipe)
def get_recipe(recipe_id: str) -> Recipe:
    return _load_recipe(recipe_id)


@router.patch("/recipes/{recipe_id}/steps/{idx}", response_model=Recipe)
def patch_step(recipe_id: str, idx: int, patch: StepPatch) -> Recipe:
    recipe = _load_recipe(recipe_id)
    try:
        step = next(s for s in recipe.steps if s.idx == idx)
    except StopIteration as e:
        raise HTTPException(status_code=404, detail=f"step {idx} not found") from e

    update = patch.model_dump(exclude_unset=True)
    if not update:
        return recipe
    for field, value in update.items():
        setattr(step, field, value)
    _save_recipe(recipe)
    return recipe


@router.post(
    "/recipes/{recipe_id}/steps/{idx}/resynthesize",
    response_model=ResynthResponse,
)
def resynth_step(recipe_id: str, idx: int, body: ResynthRequest) -> ResynthResponse:
    recipe = _load_recipe(recipe_id)
    try:
        old_step = next(s for s in recipe.steps if s.idx == idx)
    except StopIteration as e:
        raise HTTPException(status_code=404, detail=f"step {idx} not found") from e

    try:
        result = resynthesise_step(recipe, idx, body.new_intent)
    except RuntimeError as e:
        # No API key configured → surface a useful 503.
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        log.exception("resynth failed for %s/%d", recipe_id, idx)
        raise HTTPException(status_code=502, detail="resynth failed") from e

    new_step = result.step
    applied = False
    persisted_recipe: Recipe | None = None
    if body.apply:
        for i, s in enumerate(recipe.steps):
            if s.idx == idx:
                recipe.steps[i] = new_step
                break
        _save_recipe(recipe)
        applied = True
        persisted_recipe = recipe

    return ResynthResponse(
        old_step=old_step,
        new_step=new_step,
        reasoning=result.reasoning,
        applied=applied,
        recipe=persisted_recipe,
    )
