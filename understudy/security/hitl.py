"""Human-in-the-loop confirmation for risky actions.

CLI fallback. The macOS native `NSAlert` UI lives in capture/macos.py once Week 2 lands.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from rich.console import Console
from rich.prompt import Confirm

# Action classes that ALWAYS require approval, regardless of recipe metadata.
ALWAYS_CONFIRM_INTENTS: tuple[str, ...] = (
    "send",
    "delete",
    "purchase",
    "pay",
    "transfer",
    "submit",
    "publish",
    "destroy",
    "remove",
    "wipe",
)

# Domains that automatically gate every action.
SENSITIVE_DOMAINS: tuple[str, ...] = (
    "bank",
    "wellsfargo",
    "chase",
    "paypal",
    "venmo",
    "stripe",
    "coinbase",
)

Decision = Literal["approve", "deny", "abort"]


@dataclass
class Gate:
    intent: str
    detail: str
    risk: str

    def needs_confirmation(self, recipe_flag: bool) -> bool:
        if recipe_flag:
            return True
        intent_l = self.intent.lower()
        if any(w in intent_l for w in ALWAYS_CONFIRM_INTENTS):
            return True
        return any(d in self.detail.lower() for d in SENSITIVE_DOMAINS)


def confirm_action(gate: Gate, *, console: Console | None = None) -> Decision:
    """Block on user input. Returns approve / deny / abort."""
    c = console or Console()
    c.print(f"\n[bold yellow]⚠ Confirm action[/bold yellow]: {gate.intent}")
    c.print(f"  detail: {gate.detail}")
    c.print(f"  risk:   {gate.risk}")
    if not Confirm.ask("Proceed?", default=False):
        if Confirm.ask("Abort the entire run?", default=True):
            return "abort"
        return "deny"
    return "approve"


def summarize_gates(gates: Iterable[Gate]) -> str:
    items = list(gates)
    if not items:
        return "no confirmation gates"
    return "\n".join(f"  - {g.intent} ({g.risk})" for g in items)
