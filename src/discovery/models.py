from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from deterministic_ui.models import Model, Observation, ResolutionResult, Scalar, SemanticTarget


class DiscoveryAction(StrEnum):
    CLICK = "CLICK"
    FILL = "FILL"
    EXTRACT = "EXTRACT"
    WAIT = "WAIT"
    SELECT = "SELECT"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"
    REQUEST_HUMAN = "REQUEST_HUMAN"


class ModelDecision(Model):
    action: DiscoveryAction
    target_id: str | None = None
    target_description: str = Field(default="", max_length=200)
    input_binding: Literal['member_id'] | None = None
    output: Literal['savings_balance'] | None = None
    expected_text: str | None = Field(default=None, max_length=160)
    reason: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_action(self):
        targeted = self.action in {DiscoveryAction.CLICK, DiscoveryAction.FILL, DiscoveryAction.EXTRACT, DiscoveryAction.SELECT}
        if targeted != (self.target_id is not None):
            raise ValueError("Target ID required only for UI actions")
        if (self.action in {DiscoveryAction.FILL, DiscoveryAction.SELECT}) != (self.input_binding is not None):
            raise ValueError("Fill/select requires an input binding; literal values are not accepted")
        if (self.action == DiscoveryAction.EXTRACT) != (self.output is not None):
            raise ValueError("Extract requires an output name")
        if self.action in {DiscoveryAction.CLICK, DiscoveryAction.WAIT} and not self.expected_text:
            raise ValueError("Click/wait requires visible text to verify afterward")
        return self


class Usage(Model):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    thinking_tokens: int = Field(default=0, ge=0)


class ModelReply(Model):
    decision: ModelDecision
    usage: Usage = Field(default_factory=Usage)


class HistoryItem(Model):
    action: DiscoveryAction
    target_id: str | None = None
    status: str
    output_captured: str | None = None


class DiscoveryStatus(StrEnum):
    SUCCESS = "SUCCESS"
    BUSINESS_OUTCOME = "BUSINESS_OUTCOME"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    HARD_FAILURE = "HARD_FAILURE"
    STUCK = "STUCK"
    MAX_STEPS_EXCEEDED = "MAX_STEPS_EXCEEDED"


class DiscoveryLimits(Model):
    max_decisions: int = Field(default=12, ge=1, le=30)
    max_seconds: float = Field(default=120, gt=0, le=600)
    action_timeout_ms: int = Field(default=4000, ge=1, le=30000)
    repeat_limit: int = Field(default=3, ge=1, le=10)
    failure_limit: int = Field(default=3, ge=1, le=10)


class DiscoveryRequest(Model):
    goal: str = Field(min_length=1, max_length=1000)
    member_id: str = Field(pattern=r"^\d{5}$")


class TrajectoryStep(Model):
    sequence: int
    actor: Literal["MODEL"] = "MODEL"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    before: Observation
    decision: ModelDecision
    target: SemanticTarget | None = None
    resolution: ResolutionResult | None = None
    executed: bool = False
    attempted: bool = False
    verified: bool = False
    compilation_eligible: bool = False
    after: Observation | None = None
    postcondition: str = "not_verified"
    status: str = "PROPOSED"
    duration_ms: float = 0
    prior_failures: int = 0


class DiscoveryResult(Model):
    handoff_occurred: bool = False
    human_action_count: int = Field(default=0, ge=0)
    run_id: str
    status: DiscoveryStatus
    code: str
    goal: str
    provider: str
    model: str
    model_calls: int
    usage: Usage
    latency_ms: float
    outputs: dict[str, Scalar] = Field(default_factory=dict)
    trajectory: list[TrajectoryStep] = Field(default_factory=list)
    evidence_directory: str
    invocation_inputs: dict[str, Scalar] = Field(default_factory=dict, exclude=True)
