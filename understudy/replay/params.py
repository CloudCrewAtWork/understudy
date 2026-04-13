"""Parameter validation at replay start.

User-supplied `--param key=value` pairs are cast + validated against the
Recipe's declared param schema. We normalise, enforce size caps, and reject
URLs/paths that would punch through the security model.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from understudy.security.allowlist import is_allowed
from understudy.types import Recipe, RecipeParam

MAX_PARAM_LEN = 4096
MAX_CSV_BYTES = 10 * 1024 * 1024
CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f]")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class ParamError(ValueError):
    """Raised on any param validation failure. Message is user-facing."""


def validate_params(recipe: Recipe, raw: dict[str, str]) -> dict[str, str]:
    """Validate + normalise raw string params against the recipe's schema.

    Values are returned as strings (Playwright takes strings anyway). Types
    affect *validation*, not the emitted type. Unknown keys are rejected,
    missing-required raises.
    """
    schema: dict[str, RecipeParam] = {p.name: p for p in recipe.params}
    for key in raw:
        if key not in schema:
            raise ParamError(f"unknown param: {key!r}")
    out: dict[str, str] = {}
    for name, spec in schema.items():
        if name not in raw:
            if spec.required:
                raise ParamError(f"missing required param: {name!r}")
            if spec.example:
                out[name] = spec.example
            continue
        value = raw[name]
        if len(value) > MAX_PARAM_LEN:
            raise ParamError(f"param {name!r} exceeds {MAX_PARAM_LEN} bytes")
        value = CONTROL_CHARS_RE.sub("", value)
        value = unicodedata.normalize("NFC", value)
        out[name] = _validate_one(name, spec.type, value)
    return out


def _validate_one(name: str, type_: str, value: str) -> str:
    match type_:
        case "string":
            return value
        case "boolean":
            lower = value.lower()
            if lower not in {"true", "false"}:
                raise ParamError(f"param {name!r} must be 'true' or 'false'")
            return lower
        case "number":
            try:
                d = Decimal(value)
            except InvalidOperation as e:
                raise ParamError(f"param {name!r} is not a number") from e
            if not d.is_finite():
                raise ParamError(f"param {name!r} is NaN or infinite")
            if abs(d) > Decimal("1e15"):
                raise ParamError(f"param {name!r} out of range")
            return str(d)
        case "email":
            if not EMAIL_RE.match(value):
                raise ParamError(f"param {name!r} is not a valid email")
            return value
        case "url":
            try:
                parsed = urlparse(value)
            except ValueError as e:
                raise ParamError(f"param {name!r} is not a valid URL") from e
            if parsed.scheme not in {"http", "https"}:
                raise ParamError(f"param {name!r} must be http(s), got {parsed.scheme!r}")
            if not is_allowed(value):
                raise ParamError(f"param {name!r} points to a denied domain")
            return value
        case "csv_path":
            p = Path(value).expanduser().resolve()
            if not p.exists():
                raise ParamError(f"param {name!r}: file not found: {p}")
            if p.is_symlink():
                raise ParamError(f"param {name!r}: symlinks not allowed")
            if p.suffix.lower() != ".csv":
                raise ParamError(f"param {name!r} must be a .csv file")
            if p.stat().st_size > MAX_CSV_BYTES:
                raise ParamError(f"param {name!r} exceeds {MAX_CSV_BYTES} bytes")
            return str(p)
        case _:
            raise ParamError(f"param {name!r} has unknown type {type_!r}")
