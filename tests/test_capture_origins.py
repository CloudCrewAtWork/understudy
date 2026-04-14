"""Tests for capture-time origin tracking (the set that becomes the egress allowlist)."""

from __future__ import annotations

import logging

import pytest

from understudy.capture.browser import BrowserRecorder


def _make() -> BrowserRecorder:
    return BrowserRecorder(task_name="t", start_url="https://example.com/", headed=False)


def test_records_normalized_host():
    r = _make()
    r._record_origin("https://Example.COM/path")
    assert "example.com" in r._observed_origins


def test_ignores_malformed():
    r = _make()
    r._record_origin("")
    r._record_origin("not-a-url")
    r._record_origin("javascript:alert(1)")
    assert r._observed_origins == set()


def test_deny_listed_never_recorded():
    r = _make()
    r._record_origin("https://chase.com/login")
    assert r._observed_origins == set()


def test_cap_at_1024_with_warning_once(caplog: pytest.LogCaptureFixture) -> None:
    r = _make()
    # Pre-fill up to cap with unique synthetic origins.
    r._observed_origins = {f"host{i}.test" for i in range(1024)}
    with caplog.at_level(logging.WARNING, logger="understudy.capture.browser"):
        r._record_origin("https://extra-one.test/")
        r._record_origin("https://extra-two.test/")
        r._record_origin("https://extra-three.test/")
    # Set size is pinned at 1024.
    assert len(r._observed_origins) == 1024
    # Warning fires exactly once across repeated cap hits.
    cap_warnings = [
        rec for rec in caplog.records if "origin allowlist cap" in rec.getMessage()
    ]
    assert len(cap_warnings) == 1
