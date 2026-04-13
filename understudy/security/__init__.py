"""Security primitives: redaction, HITL gating, capture allowlists.

Read SECURITY.md and the README "Threat Model & Limitations" section before
loosening anything in this package.
"""

from .allowlist import DENY_DOMAINS, is_allowed
from .hitl import Decision, Gate, confirm_action
from .redact import RedactionResult, redact, redact_strict

__all__ = [
    "DENY_DOMAINS",
    "Decision",
    "Gate",
    "RedactionResult",
    "confirm_action",
    "is_allowed",
    "redact",
    "redact_strict",
]
