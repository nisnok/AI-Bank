from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field
from deterministic_ui.models import Model, Status
from capability_health.models import RunMetrics


class FailureCode(StrEnum):
    PRIMARY_LOCATOR_FAILED = "PRIMARY_LOCATOR_FAILED"
    FALLBACK_EXHAUSTED = "FALLBACK_EXHAUSTED"
    REQUIRED_ELEMENT_MISSING = "REQUIRED_ELEMENT_MISSING"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    POSTCONDITION_FAILED = "POSTCONDITION_FAILED"
    PAGE_STATE_INVALID = "PAGE_STATE_INVALID"
    PARTIAL_PAGE_LOAD = "PARTIAL_PAGE_LOAD"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    POLICY_REVIEW_REQUIRED = "POLICY_REVIEW_REQUIRED"
    ENGINE_FAILURE = "ENGINE_FAILURE"


class Scenario(Model):
    id: str
    tenant_id: Literal["bank_a","bank_b"] = "bank_a"
    drift: str = "none"
    fault: str = "NONE"
    expected_status: Status = Status.SUCCESS
    expected_failure: FailureCode | None = None
    member_id: str = Field(default="48321",exclude=True)
    expected_balance: Decimal | None = Field(default=Decimal("1420.75"),exclude=True)


class PageFacts(Model):
    expected_input_role_present: bool
    loading: bool
    unexpected_workspace: bool
    identity_matches: bool | None = None


class FailureAnalysis(Model):
    code: FailureCode | None = None
    findings: list[FailureCode] = Field(default_factory=list)
    engine_code: str | None = None
    step_id: str | None = None
    condition_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class EvaluationRun(Model):
    scenario: Scenario
    metrics: RunMetrics
    page_facts: PageFacts
    analysis: FailureAnalysis
    fallback_attempted: bool
    fallback_recovered: bool
    expectation_met: bool
    output_verified: bool | None = None


class EvaluationSummary(Model):
    capability_id: str
    capability_version: str
    canonical_digest: str
    total_runs: int
    successful_runs: int
    business_outcomes: int
    success_rate: Decimal
    primary_locator_success_rate: Decimal | None
    fallback_usage_rate: Decimal | None
    fallback_recovery_rate: Decimal | None
    fallback_attempted_runs: int
    fallback_recovered_runs: int
    unrecoverable_failure_rate: Decimal
    human_intervention_rate: Decimal
    drift_event_count: int
    expectation_pass_rate: Decimal
    failure_counts: dict[str,int]
    most_common_failure: str | None
    model_calls: int
    runs: list[EvaluationRun]
