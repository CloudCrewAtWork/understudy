import pytest
from playwright.sync_api import sync_playwright

from understudy.replay.grounding import GroundingError, ground
from understudy.types import ActionType, RecipeStep


@pytest.fixture(scope="module")
def pw():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="module")
def browser(pw):
    b = pw.chromium.launch(headless=True)
    yield b
    b.close()


@pytest.fixture()
def page(browser):
    ctx = browser.new_context()
    p = ctx.new_page()
    yield p
    ctx.close()


def _step(role: str, name: str, action: ActionType = ActionType.CLICK) -> RecipeStep:
    return RecipeStep(idx=1, intent="noop", action=action, aria_role=role, aria_name=name)


def test_exact_match_single_button(page):
    page.set_content("<button aria-label='Send'>Send</button>")
    loc = ground(page, _step("button", "Send"))
    assert loc is not None
    assert loc.count() == 1


def test_ambiguous_picks_visible(page):
    page.set_content("<button hidden>Submit</button><button>Submit</button>")
    loc = ground(page, _step("button", "Submit"))
    assert loc is not None
    assert loc.is_visible()


def test_textbox_label_fallback(page):
    page.set_content("<label for='e'>Email</label><input id='e' type='email'>")
    loc = ground(page, _step("textbox", "Email", action=ActionType.TYPE))
    assert loc is not None


def test_zero_matches_raises(page):
    page.set_content("<p>just prose, no button</p>")
    with pytest.raises(GroundingError):
        ground(page, _step("button", "Ghost"))


def test_nav_action_needs_no_element(page):
    step = RecipeStep(idx=1, intent="open", action=ActionType.NAV)
    assert ground(page, step) is None


def test_link_text_fallback(page):
    page.set_content('<a href="#">Learn more</a>')
    # aria_role=link with name only as visible text.
    loc = ground(page, _step("link", "Learn more"))
    assert loc is not None
