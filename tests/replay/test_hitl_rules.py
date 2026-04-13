from understudy.replay.hitl_rules import known_domains, must_confirm
from understudy.replay.result import StepOutcome, StepStatus
from understudy.types import ActionType, RecipeStep


def _step(
    intent: str = "click something",
    action: ActionType = ActionType.CLICK,
    requires: bool = False,
    aria_name: str | None = None,
) -> RecipeStep:
    return RecipeStep(
        idx=1, intent=intent, action=action, requires_confirmation=requires, aria_name=aria_name
    )


def _outcome(i: int) -> StepOutcome:
    return StepOutcome(idx=i, intent="ok", status=StepStatus.OK, ms=10)


def test_requires_confirmation_fires():
    needs, _ = must_confirm(
        _step(requires=True),
        current_url="https://a.com/",
        recipe_known_domains=frozenset({"a.com"}),
        completed=[],
    )
    assert needs is True


def test_destructive_verb_in_intent():
    needs, reason = must_confirm(
        _step(intent="click Send Campaign"),
        current_url="https://a.com/",
        recipe_known_domains=frozenset({"a.com"}),
        completed=[],
    )
    assert needs is True
    assert "destructive" in reason


def test_nav_to_new_domain():
    step = RecipeStep(
        idx=2,
        intent="go to dashboard",
        action=ActionType.NAV,
        aria_name="https://other.com/",
    )
    needs, _ = must_confirm(
        step, current_url="https://a.com/", recipe_known_domains=frozenset({"a.com"}), completed=[]
    )
    assert needs is True


def test_current_page_not_in_known_domains():
    needs, _ = must_confirm(
        _step(),
        current_url="https://unexpected.com/",
        recipe_known_domains=frozenset({"a.com"}),
        completed=[],
    )
    assert needs is True


def test_benign_click_on_known_domain():
    needs, _ = must_confirm(
        _step(),
        current_url="https://a.com/",
        recipe_known_domains=frozenset({"a.com"}),
        completed=[],
    )
    assert needs is False


def test_heartbeat_fires():
    completed = [_outcome(i) for i in range(1, 26)]  # 25 completed
    needs, reason = must_confirm(
        _step(),
        current_url="https://a.com/",
        recipe_known_domains=frozenset({"a.com"}),
        completed=completed,
    )
    assert needs is True
    assert "heartbeat" in reason


def test_known_domains_extraction():
    out = known_domains(
        [
            "https://app.example.com/",
            "https://app.example.com/nested",
            "https://other.com/",
            "about:blank",
        ]
    )
    assert out == frozenset({"app.example.com", "other.com"})
