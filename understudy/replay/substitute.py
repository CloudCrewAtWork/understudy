"""Safe value-template substitution.

`str.format` with user-controlled parameter names is a known attack surface
(`{__class__}`, `{0.__init__.__globals__}`, etc.). We use a restricted formatter
that rejects attribute access and indexing.
"""

from __future__ import annotations

import string


class MissingParamError(KeyError):
    """Raised when a template references a param the user did not supply."""


MAX_RENDERED_LEN = 16 * 1024  # hard cap on total rendered template output


class _SafeFormatter(string.Formatter):
    def get_field(self, field_name: str, args: object, kwargs: object) -> tuple[object, str]:
        if "." in field_name or "[" in field_name or "]" in field_name:
            raise ValueError(f"nested access blocked in template: {field_name!r}")
        if not isinstance(kwargs, dict):
            raise TypeError("params must be a dict")
        if field_name not in kwargs:
            raise MissingParamError(field_name)
        return kwargs[field_name], field_name

    def convert_field(self, value: object, conversion: str | None) -> object:
        # Reject !r, !s, !a conversions to keep outputs predictable.
        if conversion is not None:
            raise ValueError(f"conversion {conversion!r} is not allowed in templates")
        return value

    def format_field(self, value: object, format_spec: str) -> str:
        # Reject custom format specs to prevent width-based DoS and locale tricks.
        if format_spec:
            raise ValueError(f"format spec {format_spec!r} is not allowed in templates")
        return str(value)


_FMT = _SafeFormatter()


def render_template(template: str | None, params: dict[str, str]) -> str:
    """Substitute `{name}` placeholders with values from params.

    Returns the empty string when template is None/empty (action had no value).
    Raises MissingParamError when a placeholder has no matching param.
    """
    if not template:
        return ""
    rendered = _FMT.vformat(template, (), params)
    if len(rendered) > MAX_RENDERED_LEN:
        raise ValueError(f"rendered template exceeds {MAX_RENDERED_LEN} bytes")
    return rendered
