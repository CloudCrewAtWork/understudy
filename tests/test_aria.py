from understudy.capture.aria import aria_ref, find_anchor, normalize_name


def test_normalize_name_collapses_whitespace():
    assert normalize_name("  Hello   World  ") == "hello world"


def test_aria_ref_stable_across_runs():
    a = aria_ref("button", "Sign in", [0, 1, 2])
    b = aria_ref("button", "Sign in", [0, 1, 2])
    assert a == b
    assert len(a) == 16


def test_aria_ref_changes_on_role():
    a = aria_ref("button", "X", [0])
    b = aria_ref("link", "X", [0])
    assert a != b


def test_find_anchor_walks_tree():
    snap = {
        "role": "WebArea",
        "name": "Page",
        "children": [
            {"role": "button", "name": "Sign in"},
            {"role": "link", "name": "Help", "children": []},
        ],
    }
    target = aria_ref("button", "Sign in", [0])
    found = find_anchor(snap, target)
    assert found is not None
    assert found["name"] == "Sign in"


def test_find_anchor_returns_none_when_missing():
    snap = {"role": "WebArea", "name": "x", "children": []}
    assert find_anchor(snap, "deadbeef") is None
