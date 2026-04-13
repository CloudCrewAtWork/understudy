"""Audit log for replay runs. Hashes sensitive values before storage."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from understudy.db import session


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def hash_value(v: str | None) -> str | None:
    if v is None:
        return None
    return hashlib.sha256(v.encode("utf-8", errors="replace")).hexdigest()[:16]


def etld1(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host or None


def log_event(run_id: str, event: str, **detail: Any) -> None:
    """Append one row to audit_log. Callers must not pass raw PII in `detail`."""
    payload = {"run_id": run_id, **detail}
    with session() as conn:
        conn.execute(
            "INSERT INTO audit_log (ts, event, detail_json) VALUES (?, ?, ?)",
            (_now(), event, json.dumps(payload, separators=(",", ":"))),
        )
