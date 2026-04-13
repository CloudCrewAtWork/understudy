"""FastAPI TestClient-based tests for the UI server.

No real browser, no real Claude call — we monkeypatch resynth to keep tests
deterministic and offline.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from understudy import db
from understudy.server.app import create_app
from understudy.server.resynth import ResynthResult
from understudy.server.security import SessionSecurity
from understudy.types import ActionType, Recipe, RecipeParam, RecipeStep, TargetKind

CSRF = "unit-test-token"
PORT = 8765


def _recipe() -> Recipe:
    return Recipe(
        id="rid",
        task_name="demo_search",
        target_kind=TargetKind.BROWSER,
        source_trajectory_id="tid",
        induced_by="test",
        description="a trivial fixture recipe",
        params=[RecipeParam(name="query", type="string", description="the query")],
        steps=[
            RecipeStep(
                idx=1,
                intent="open example",
                action=ActionType.NAV,
                value_template="https://example.com/",
            ),
            RecipeStep(
                idx=2,
                intent="type the query",
                action=ActionType.TYPE,
                aria_role="textbox",
                aria_name="Search",
                value_template="{query}",
            ),
        ],
    )


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """Spin up a test client with an isolated SQLite DB."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("UNDERSTUDY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNDERSTUDY_DB_PATH", str(db_path))

    # Clear the settings cache so env overrides take effect.
    import understudy.config as cfg

    cfg._settings = None

    r = _recipe()
    with db.session() as conn:
        # Seed a parent trajectory row so the recipe FK is satisfied.
        from understudy.types import Trajectory

        traj = Trajectory(id="tid", task_name="demo_search")
        db.insert_trajectory(conn, traj, tmp_path / "tid.jsonl")
        db.insert_recipe(conn, r)

    session = SessionSecurity(csrf_token=CSRF, host="127.0.0.1", port=PORT)
    app = create_app(session=session)
    with TestClient(app, base_url=f"http://127.0.0.1:{PORT}") as c:
        # TestClient sets Host from base_url; make sure Origin is also set
        # for mutation tests.
        yield c


def _mut_headers() -> dict[str, str]:
    return {
        "X-Understudy-CSRF": CSRF,
        "Origin": f"http://127.0.0.1:{PORT}",
        "Sec-Fetch-Site": "same-origin",
    }


def test_list_recipes(client: TestClient) -> None:
    r = client.get("/api/recipes")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["task_name"] == "demo_search"
    assert data[0]["step_count"] == 2


def test_get_recipe_shape(client: TestClient) -> None:
    r = client.get("/api/recipes/rid")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "rid"
    assert len(body["steps"]) == 2
    assert body["steps"][1]["value_template"] == "{query}"


def test_patch_step_updates_intent(client: TestClient) -> None:
    r = client.patch(
        "/api/recipes/rid/steps/2",
        json={"intent": "type the search term carefully"},
        headers=_mut_headers(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    step2 = next(s for s in body["steps"] if s["idx"] == 2)
    assert step2["intent"] == "type the search term carefully"


def test_patch_rejects_unknown_step(client: TestClient) -> None:
    r = client.patch(
        "/api/recipes/rid/steps/999",
        json={"intent": "x"},
        headers=_mut_headers(),
    )
    assert r.status_code == 404


def test_mutation_without_csrf_rejected(client: TestClient) -> None:
    r = client.patch(
        "/api/recipes/rid/steps/2",
        json={"intent": "x"},
        headers={
            "Origin": f"http://127.0.0.1:{PORT}",
            "Sec-Fetch-Site": "same-origin",
        },
    )
    assert r.status_code == 403


def test_mutation_with_cross_site_rejected(client: TestClient) -> None:
    r = client.patch(
        "/api/recipes/rid/steps/2",
        json={"intent": "x"},
        headers={
            "X-Understudy-CSRF": CSRF,
            "Origin": "https://evil.com",
            "Sec-Fetch-Site": "cross-site",
        },
    )
    assert r.status_code == 403


def test_mutation_with_bad_origin_rejected(client: TestClient) -> None:
    r = client.patch(
        "/api/recipes/rid/steps/2",
        json={"intent": "x"},
        headers={
            "X-Understudy-CSRF": CSRF,
            "Origin": "https://evil.com",
            "Sec-Fetch-Site": "same-origin",
        },
    )
    assert r.status_code == 403


def test_resynth_preview_does_not_mutate(client: TestClient, monkeypatch) -> None:
    def fake_resynth(recipe, idx, new_intent):
        return ResynthResult(
            step=RecipeStep(
                idx=idx,
                intent=new_intent,
                action=ActionType.TYPE,
                aria_role="textbox",
                aria_name="Search",
                value_template="{query}",
            ),
            reasoning="test reasoning",
            raw="{}",
        )

    monkeypatch.setattr("understudy.server.routes.recipes.resynthesise_step", fake_resynth)

    r = client.post(
        "/api/recipes/rid/steps/2/resynthesize",
        json={"new_intent": "carefully type the search term", "apply": False},
        headers=_mut_headers(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is False
    assert body["reasoning"] == "test reasoning"
    assert body["new_step"]["intent"] == "carefully type the search term"

    # DB must be unchanged.
    db_step = client.get("/api/recipes/rid").json()["steps"][1]
    assert db_step["intent"] == "type the query"


def test_resynth_apply_persists(client: TestClient, monkeypatch) -> None:
    def fake_resynth(recipe, idx, new_intent):
        return ResynthResult(
            step=RecipeStep(
                idx=idx,
                intent=new_intent,
                action=ActionType.TYPE,
                aria_role="textbox",
                aria_name="Search",
                value_template="{query}",
                success_check="the search is submitted",
            ),
            reasoning=None,
            raw="{}",
        )

    monkeypatch.setattr("understudy.server.routes.recipes.resynthesise_step", fake_resynth)

    r = client.post(
        "/api/recipes/rid/steps/2/resynthesize",
        json={"new_intent": "improved intent", "apply": True},
        headers=_mut_headers(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] is True
    assert body["new_step"]["success_check"] == "the search is submitted"
    db_step = client.get("/api/recipes/rid").json()["steps"][1]
    assert db_step["intent"] == "improved intent"
