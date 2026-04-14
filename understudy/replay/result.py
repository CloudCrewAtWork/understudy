"""Result types for a replay run. Serialisable JSON so the CLI can post-summarize."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class StepStatus(StrEnum):
    OK = "ok"
    SOFT_FAIL = "soft_fail"  # success_check heuristic failed, action executed
    ERROR = "error"  # exception during grounding or action
    ABORTED = "aborted"  # user denied or HITL auto-deny
    BUDGET = "budget"  # budget cap tripped


class AbortReason(StrEnum):
    USER = "user"
    BUDGET = "budget"
    DOMAIN_DRIFT = "domain_drift"
    CAPTCHA = "captcha"
    AUTH_REQUIRED = "auth_required"
    RECIPE_INVARIANT = "recipe_invariant"
    PARAM_ERROR = "param_error"
    UNKNOWN = "unknown"


class StepOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idx: int
    intent: str
    status: StepStatus
    ms: int
    url_etld1: str | None = None
    target_hint: str | None = None
    error: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    retries: int = 0
    # Text extracted from a `note` step's grounded element. Only populated
    # for note actions; all others remain None.
    extracted: str | None = None


class ReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    recipe_id: str
    task_name: str
    started_at: str = Field(default_factory=_now)
    finished_at: str | None = None
    status: Literal["ok", "partial", "aborted", "error"] = "ok"
    abort_reason: AbortReason | None = None
    steps_total: int = 0
    steps_done: int = 0
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    llm_calls: int = 0
    outcomes: list[StepOutcome] = Field(default_factory=list)
    log_path: str | None = None

    @property
    def success_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        passed = sum(1 for o in self.outcomes if o.status == StepStatus.OK)
        return passed / len(self.outcomes)
