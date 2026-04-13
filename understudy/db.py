"""SQLite (optionally SQLCipher-encrypted) connection + schema bootstrap.

Encryption rules (security floor — do not relax without a review):

1. PRAGMA key MUST run before any other statement.
2. After PRAGMA key, we run a smoke read to verify the key actually decrypts.
   If it doesn't, we abort. We never silently fall through to plaintext.
3. If the SQLCipher driver is unavailable AND a key was configured, we abort
   loudly. Plaintext is only allowed when the user explicitly opted out by
   leaving every key source empty.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import get_settings
from .types import Recipe, Trajectory

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
HEX_RE = re.compile(r"^[0-9a-f]+$")


class EncryptionError(RuntimeError):
    """Raised when the configured DB key is rejected or unavailable."""


def _try_sqlcipher() -> tuple[Any, bool]:
    try:
        import sqlcipher3  # type: ignore[import-not-found]

        return sqlcipher3, True
    except ImportError:
        return sqlite3, False


def _resolve_db_key() -> str | None:
    s = get_settings()
    if s.db_key and s.db_key.get_secret_value():
        return s.db_key.get_secret_value()
    try:
        import keyring

        key = keyring.get_password("understudy", "db_key")
        return key
    except Exception as e:
        log.warning("keyring unavailable, db will be plaintext if no env key: %s", e)
        return None


def _to_hex(s: str) -> str:
    return s.encode("utf-8").hex()


def connect() -> sqlite3.Connection:
    s = get_settings()
    driver, has_cipher = _try_sqlcipher()
    db_path = s.expanded_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    key = _resolve_db_key()

    if key and not has_cipher:
        # Don't lull the user. If they configured a key, they expect encryption.
        raise EncryptionError(
            "DB key configured but sqlcipher3 is not installed. "
            "Install with: brew install sqlcipher && uv sync --extra crypto"
        )

    conn: sqlite3.Connection = driver.connect(str(db_path), isolation_level=None)
    if has_cipher and key:
        hexkey = _to_hex(key)
        if not HEX_RE.fullmatch(hexkey):
            raise EncryptionError("invalid hex key derivation")
        # Single-quoted blob literal, double-quoted PRAGMA value: the SQLCipher form.
        conn.execute(f"PRAGMA key = \"x'{hexkey}'\"")
        conn.execute("PRAGMA cipher_compatibility = 4")
        conn.execute("PRAGMA cipher_page_size = 4096")
        conn.execute("PRAGMA kdf_iter = 256000")
        # Smoke read to confirm the key is correct. On failure SQLCipher raises.
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlite3.DatabaseError as e:
            conn.close()
            raise EncryptionError("PRAGMA key was rejected (wrong key or corrupt DB)") from e

    conn.execute("PRAGMA journal_mode = WAL")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def insert_trajectory(conn: sqlite3.Connection, t: Trajectory, file_path: Path) -> None:
    conn.execute(
        """
        INSERT INTO trajectories (id, task_name, target_kind, started_at, finished_at,
                                  success, step_count, notes, file_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            t.id,
            t.task_name,
            t.target_kind.value,
            t.started_at,
            t.finished_at,
            int(t.success) if t.success is not None else None,
            len(t.steps),
            t.notes,
            str(file_path),
        ),
    )


def insert_recipe(conn: sqlite3.Connection, r: Recipe) -> None:
    conn.execute(
        """
        INSERT INTO recipes (id, task_name, target_kind, source_traj_id, induced_by,
                             created_at, recipe_json, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            r.id,
            r.task_name,
            r.target_kind.value,
            r.source_trajectory_id,
            r.induced_by,
            r.created_at,
            r.model_dump_json(),
        ),
    )


def audit(conn: sqlite3.Connection, event: str, **detail: object) -> None:
    conn.execute(
        "INSERT INTO audit_log (ts, event, detail_json) VALUES (?, ?, ?)",
        (
            datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            event,
            json.dumps(detail),
        ),
    )
