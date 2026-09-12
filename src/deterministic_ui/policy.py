from pydantic import Field

from .models import CapabilityArtifact, CapabilityLifecycle, Decision, Model, ResolutionResult, Risk, Step


RISK_ORDER = {risk: index for index, risk in enumerate(Risk)}


class PolicyConfig(Model):
    decisions: dict[Risk, Decision] = Field(default_factory=lambda: {
        Risk.READ: Decision.ALLOW,
        Risk.REVERSIBLE_WRITE: Decision.ALLOW,
        Risk.SENSITIVE: Decision.REQUIRE_HUMAN,
        Risk.IRREVERSIBLE: Decision.BLOCK,
    })


class PolicyResult(Model):
    decision: Decision
    code: str


class PolicyEngine:
    def __init__(self, config: PolicyConfig | None = None):
        self.config = config or PolicyConfig()

    def evaluate(self, artifact: CapabilityArtifact, step: Step,
                 resolution: ResolutionResult) -> PolicyResult:
        if not resolution.succeeded:
            return PolicyResult(decision=Decision.BLOCK, code="UNRESOLVED_TARGET")
        if artifact.lifecycle == CapabilityLifecycle.DRAFT:
            return PolicyResult(decision=Decision.REQUIRE_HUMAN, code="DRAFT_REQUIRES_VALIDATION")
        validated_low_risk = (artifact.lifecycle == CapabilityLifecycle.VALIDATED
                              and artifact.provenance is not None
                              and artifact.provenance.validation_run_id is not None
                              and RISK_ORDER[artifact.safety.max_risk] <= RISK_ORDER[Risk.REVERSIBLE_WRITE])
        if not artifact.safety.approved_for_replay and not validated_low_risk:
            return PolicyResult(decision=Decision.REQUIRE_HUMAN, code="ARTIFACT_NOT_APPROVED")
        if RISK_ORDER[step.risk] > RISK_ORDER[artifact.safety.max_risk]:
            return PolicyResult(decision=Decision.BLOCK, code="RISK_EXCEEDS_ARTIFACT_LIMIT")
        return self.evaluate_operation(step.risk, resolution)

    def evaluate_operation(self, risk: Risk, resolution: ResolutionResult, *,
                           unreviewed: bool = False) -> PolicyResult:
        """Shared policy gate; discovery has no approved artifact to authorize risky writes."""
        if not resolution.succeeded:
            return PolicyResult(decision=Decision.BLOCK, code="UNRESOLVED_TARGET")
        return self.evaluate_risk(risk, unreviewed=unreviewed)

    def evaluate_risk(self, risk: Risk, *, unreviewed: bool = False) -> PolicyResult:
        """Also gates target-free read operations such as semantic waiting."""
        if unreviewed and risk in {Risk.SENSITIVE, Risk.IRREVERSIBLE}:
            return PolicyResult(decision=Decision.REQUIRE_HUMAN, code="UNREVIEWED_RISK")
        decision = self.config.decisions.get(risk, Decision.BLOCK)
        # A unique fallback remains eligible. Historical health is not a kill switch.
        return PolicyResult(decision=decision, code=f"RISK_{decision.value}")
