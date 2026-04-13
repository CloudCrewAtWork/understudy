"""Text redaction. Runs on every captured text/value/screenshot-OCR before storage or API send.

Two layers:
1. Fast regex (always on) — catches structured PII (cards, SSN, OTP, JWT, bearer, common keys).
2. Optional Presidio NER (settings.redaction_strict) — catches names/emails/addresses.

Goals: zero false-negatives on credentials, accept some over-redaction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from re import Pattern

# Patterns adapted from gitleaks/trufflehog public rulesets.
# Conservative: false positives are fine, false negatives are not.
PATTERNS: dict[str, Pattern[str]] = {
    "credit_card_loose": re.compile(r"\b(?:\d[ -]?){12,18}\d\b"),
    "credit_card_strict": re.compile(r"\b\d{13,19}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "otp": re.compile(r"\b(?:OTP|2FA|verification\s*code)[^\d]{0,12}(\d{4,8})\b", re.I),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "bearer": re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}", re.I),
    "anthropic_key": re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"),
    "openai_proj_key": re.compile(r"\bsk-proj-[A-Za-z0-9_\-]{20,}\b"),
    "openai_svc_key": re.compile(r"\bsk-svcacct-[A-Za-z0-9_\-]{20,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "aws_secret_key_labelled": re.compile(
        r"(?i)(?:aws[_-]?(?:secret|access)|secret[_-]?access)[_-]?key"
        r"[\"=:\s]+([A-Za-z0-9/+=]{40})"
    ),
    "github_pat": re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    "github_oauth": re.compile(r"\bgho_[A-Za-z0-9]{36}\b"),
    "github_user_token": re.compile(r"\bghu_[A-Za-z0-9]{36}\b"),
    "github_server_token": re.compile(r"\bghs_[A-Za-z0-9]{36}\b"),
    "github_refresh": re.compile(r"\bghr_[A-Za-z0-9]{36}\b"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]+\b"),
    "stripe_key": re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{20,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|DSA|PRIVATE) KEY-----"),
    "password_field": re.compile(r"(?i)\bpassword\b\s*[:=]\s*\S+"),
}

# Patterns where we want to keep the original substring matchable for tests.
LUHN_PATTERNS = ("credit_card_loose", "credit_card_strict")

REDACT_TOKEN = "[REDACTED:{kind}]"  # noqa: S105 — not a credential, the substitution template


@dataclass(frozen=True)
class RedactionResult:
    text: str
    hits: tuple[tuple[str, int], ...]

    @property
    def changed(self) -> bool:
        return bool(self.hits)


def _luhn(digits: str) -> bool:
    n = [int(c) for c in digits if c.isdigit()]
    if len(n) < 13:
        return False
    checksum = 0
    parity = len(n) % 2
    for i, d in enumerate(n):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def redact(text: str | None) -> RedactionResult:
    """Apply all regex rules. Returns redacted text + hit summary."""
    if text is None or text == "":
        return RedactionResult("" if text is None else text, ())

    out = text
    hits: dict[str, int] = {}
    for kind, pat in PATTERNS.items():
        if kind in LUHN_PATTERNS:

            def _sub(m: re.Match[str], _kind: str = kind) -> str:
                if _luhn(m.group(0)):
                    hits[_kind] = hits.get(_kind, 0) + 1
                    return REDACT_TOKEN.format(kind=_kind)
                return m.group(0)

            out = pat.sub(_sub, out)
        else:
            new, n = pat.subn(REDACT_TOKEN.format(kind=kind), out)
            if n:
                hits[kind] = hits.get(kind, 0) + n
                out = new
    return RedactionResult(out, tuple(hits.items()))


@lru_cache(maxsize=1)
def _presidio_engine() -> tuple[object, object] | None:
    """Lazy: Presidio + spaCy load is slow. Only on first NER call."""
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        return AnalyzerEngine(), AnonymizerEngine()
    except Exception:
        return None


def redact_strict(text: str | None) -> RedactionResult:
    """Regex + Presidio NER. Run async / batched, NOT in capture hot path."""
    base = redact(text)
    engine = _presidio_engine()
    if engine is None or not base.text:
        return base
    analyzer, anonymizer = engine
    try:
        results = analyzer.analyze(text=base.text, language="en")  # type: ignore[attr-defined]
        if not results:
            return base
        anon = anonymizer.anonymize(text=base.text, analyzer_results=results).text  # type: ignore[attr-defined]
        return RedactionResult(anon, base.hits + tuple((r.entity_type, 1) for r in results))
    except Exception:
        return base
