from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator
from deterministic_ui.models import Model, Status


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class RunMetrics(Model):
    run_id: str
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    capability_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    tenant_id: str
    binding_version: str | None = None
    started_at: datetime
    completed_at: datetime
    status: Status
    duration_ms: Decimal | None = None
    step_count: int = 0
    primary_locator_attempts: int = 0
    primary_locator_successes: int = 0
    fallback_locator_successes: int = 0
    maximum_fallback_depth: int = 0
    ambiguity_count: int = 0
    recoverable_error_count: int = 0
    recovery_attempts: int = 0
    successful_recovery_count: int = 0
    human_handoff_count: int = 0
    human_action_count: int = 0
    drift_signal_count: int = 0
    validation_outcome: Status | None = None
    model_calls: int = 0
    evidence_directory: str
    evidence_digest: str

    @model_validator(mode="after")
    def coherent(self):
        counts = [self.step_count, self.primary_locator_attempts, self.primary_locator_successes,
                  self.fallback_locator_successes, self.maximum_fallback_depth, self.ambiguity_count,
                  self.recoverable_error_count, self.recovery_attempts, self.successful_recovery_count,
                  self.human_handoff_count, self.human_action_count, self.drift_signal_count, self.model_calls]
        if any(count < 0 for count in counts):
            raise ValueError("NEGATIVE_METRIC")
        if self.primary_locator_successes + self.fallback_locator_successes > self.primary_locator_attempts:
            raise ValueError("INVALID_LOCATOR_COUNTS")
        if self.successful_recovery_count > self.recovery_attempts:
            raise ValueError("INVALID_RECOVERY_COUNTS")
        if self.completed_at < self.started_at or (self.duration_ms is not None and self.duration_ms < 0):
            raise ValueError("INVALID_RUN_TIME")
        return self


class EvidenceIssue(Model):
    evidence_directory: str
    code: str


class Thresholds(Model):
    minimum_runs: int = Field(default=5, ge=1)
    recent_window: int = Field(default=5, ge=1, le=100)
    historical_window: int = Field(default=5, ge=1, le=100)
    maximum_fallback_rate: Decimal = Field(default=Decimal(".10"), ge=0, le=1)
    minimum_primary_rate: Decimal = Field(default=Decimal(".90"), ge=0, le=1)
    maximum_recovery_rate: Decimal = Field(default=Decimal(".10"), ge=0, le=1)
    maximum_intervention_rate: Decimal = Field(default=Decimal(".10"), ge=0, le=1)
    unhealthy_failure_rate: Decimal = Field(default=Decimal(".10"), gt=0, le=1)
    unhealthy_ambiguity_rate: Decimal = Field(default=Decimal(".10"), gt=0, le=1)
    minimum_repeated_failures: int = Field(default=2, ge=2)
    minimum_reliable_completion_rate: Decimal = Field(default=Decimal(".80"), ge=0, le=1)
    trend_rate_delta: Decimal = Field(default=Decimal(".15"), gt=0, le=1)
    latency_ratio: Decimal = Field(default=Decimal("1.5"), gt=1)
    latency_minimum_increase_ms: Decimal = Field(default=Decimal("100"), ge=0)


class HealthReason(Model):
    code: str
    metric: str
    observed: Decimal | None = None
    threshold: Decimal | None = None
    previous: Decimal | None = None
    recent: Decimal | None = None
    tenant_id: str | None = None


class Assessment(Model):
    total_runs: int
    successful_runs: int
    business_outcomes: int
    hard_failures: int
    human_required_runs: int
    success_rate: Decimal  # SUCCESS + BUSINESS_OUTCOME: reliable automation completion.
    primary_locator_match_rate: Decimal | None
    fallback_rate: Decimal | None
    primary_locator_attempts: int
    primary_locator_successes: int
    fallback_locator_successes: int
    maximum_fallback_depth: int
    recovery_attempts: int
    recoverable_errors: int
    successful_recoveries: int
    recovery_rate: Decimal
    human_handoff_count: int
    human_action_count: int
    human_intervention_rate: Decimal
    ambiguity_count: int
    ambiguity_rate: Decimal
    hard_failure_rate: Decimal
    drift_signal_count: int
    drift_rate: Decimal
    average_latency_ms: Decimal | None
    p95_latency_ms: Decimal | None
    latency_samples: int
    validation_runs: int
    validation_successes: int
    model_calls: int
    binding_versions: list[str]
    status: HealthStatus
    reasons: list[HealthReason]
    recommendation: str
    run_ids: list[str]
    historical_run_ids: list[str] = Field(default_factory=list)
    recent_run_ids: list[str] = Field(default_factory=list)


class TenantHealth(Assessment):
    tenant_id: str


class CapabilityHealth(Assessment):
    capability_id: str
    capability_version: str
    generated_at: datetime
    tenant_health: list[TenantHealth]
    thresholds: Thresholds
    evidence_issues: list[EvidenceIssue] = Field(default_factory=list)
    derived_data: bool = True
