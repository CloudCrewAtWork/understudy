"""ARIA snapshot helpers — stable cross-run anchors for elements.

aria_ref = sha1(role | normalized_name | sibling-index path).
This survives most non-structural DOM churn (class renames, ad-injections, attr changes).
"""

from __future__ import annotations

import hashlib
from typing import Any


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return " ".join(name.split()).strip().lower()[:120]


def aria_ref(role: str | None, name: str | None, path: list[int] | None = None) -> str:
    """Build a stable id for an aria node."""
    parts = [(role or "").lower(), normalize_name(name)]
    if path:
        parts.append(",".join(str(i) for i in path))
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:16]


def snapshot_hash(snapshot: Any) -> str:
    """Stable hash of an entire aria snapshot. Used to detect page-state drift."""
    s = repr(snapshot).encode("utf-8")
    return hashlib.sha1(s, usedforsecurity=False).hexdigest()[:16]


def find_anchor(snapshot: Any, ref: str) -> dict[str, Any] | None:
    """Walk a Playwright accessibility snapshot looking for a node whose ref matches."""
    if not snapshot:
        return None

    def _walk(node: dict[str, Any], path: list[int]) -> dict[str, Any] | None:
        node_ref = aria_ref(node.get("role"), node.get("name"), path)
        if node_ref == ref:
            return node
        for i, child in enumerate(node.get("children", []) or []):
            hit = _walk(child, [*path, i])
            if hit:
                return hit
        return None

    return _walk(snapshot, [])
