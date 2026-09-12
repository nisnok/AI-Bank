"""Validation replay has no dependency on discovery, models, or a compiler implementation."""
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path

from deterministic_ui.models import (CapabilityArtifact, CapabilityLifecycle, Decision, Model,
                                     ResolutionResult, Risk, RunResult, Scalar, Status, Step)
from deterministic_ui.policy import PolicyEngine, PolicyResult, RISK_ORDER
from deterministic_ui.replay import ReplayEngine
from deterministic_ui.surface import Surface
from deterministic_ui.templates import bind_conditions, validate_inputs


def artifact_digest(artifact: CapabilityArtifact) -> str:
    return sha256(artifact.model_dump_json().encode()).hexdigest()


class DraftValidationPolicy(PolicyEngine):
    """Explicit validation authority scoped to one draft and low-risk operations."""
    def __init__(self, artifact: CapabilityArtifact, inputs: Mapping[str, Scalar]):
        super().__init__()
        if artifact.lifecycle != CapabilityLifecycle.DRAFT or artifact.provenance is None:
            raise ValueError('GENERATED_DRAFT_REQUIRED')
        bound = bind_conditions(artifact, inputs)
        self._digest = artifact_digest(bound)
        self._steps = {step.id:step for step in bound.steps}

    def evaluate(self, artifact: CapabilityArtifact, step: Step, resolution: ResolutionResult) -> PolicyResult:
        if artifact_digest(artifact) != self._digest or self._steps.get(step.id) != step:
            return PolicyResult(decision=Decision.BLOCK, code='VALIDATION_SCOPE_MISMATCH')
        if RISK_ORDER[step.risk] > RISK_ORDER[Risk.REVERSIBLE_WRITE]:
            return PolicyResult(decision=Decision.BLOCK, code='VALIDATION_RISK_BLOCKED')
        return self.evaluate_operation(step.risk, resolution)


class ValidationResult(Model):
    artifact: CapabilityArtifact
    replay: RunResult | None = None
    different_inputs: bool
    code: str
    draft_digest: str


class CapabilityValidator:
    async def validate(self, artifact: CapabilityArtifact, discovery_inputs: Mapping[str, Scalar],
                       validation_inputs: Mapping[str, object], surface: Surface,
                       *, evidence_root: Path = Path('evidence/validation')) -> ValidationResult:
        if artifact.lifecycle != CapabilityLifecycle.DRAFT or artifact.provenance is None:
            raise ValueError('GENERATED_DRAFT_REQUIRED')
        source = validate_inputs(artifact.inputs, discovery_inputs)
        inputs = validate_inputs(artifact.inputs, validation_inputs)
        digest = artifact_digest(artifact)
        if source == inputs:
            return ValidationResult(artifact=artifact, different_inputs=False,
                                    code='DIFFERENT_INPUTS_REQUIRED', draft_digest=digest)
        replay = await ReplayEngine(surface, policy=DraftValidationPolicy(artifact, inputs), evidence_root=evidence_root).execute(artifact, inputs)
        if replay.status != Status.SUCCESS:
            return ValidationResult(artifact=artifact, replay=replay, different_inputs=True,
                                    code='VALIDATION_FAILED', draft_digest=digest)
        validated = artifact.model_copy(update={'lifecycle':CapabilityLifecycle.VALIDATED,
            'provenance':artifact.provenance.model_copy(update={'validation_run_id':replay.run_id})})
        return ValidationResult(artifact=validated, replay=replay, different_inputs=True,
                                code='VALIDATED', draft_digest=digest)
