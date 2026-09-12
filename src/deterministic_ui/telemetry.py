"""Per-resolution observations, not aggregate capability health scores."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field
from .models import Model, Status


class LocatorTelemetry(Model):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str
    capability_id: str
    capability_version: str
    tenant_id: str
    binding_version: str
    step_id: str | None
    condition_id: str | None = None
    expected_primary_strategy: str
    primary_strategy_succeeded: bool
    strategy_used: str | None
    attempted_strategy: str | None
    fallback_depth: int
    match_count: int
    resolution_quality: str
    ambiguity: bool
    resolution_succeeded: bool
    recovery_needed: bool
    retry_needed: bool = False
    step_execution_result: Status | None = None
    execution_result: Status | None = None


class DriftSignal(LocatorTelemetry):
    reason: Literal["FALLBACK_USED", "AMBIGUOUS_TARGET"]
