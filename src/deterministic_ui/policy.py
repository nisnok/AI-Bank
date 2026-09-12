from pydantic import Field

from .models import CapabilityArtifact, Decision, Model, ResolutionResult, Risk, Step


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
        if not artifact.safety.approved_for_replay:
            return PolicyResult(decision=Decision.REQUIRE_HUMAN, code="ARTIFACT_NOT_APPROVED")
        if RISK_ORDER[step.risk] > RISK_ORDER[artifact.safety.max_risk]:
            return PolicyResult(decision=Decision.BLOCK, code="RISK_EXCEEDS_ARTIFACT_LIMIT")
        decision = self.config.decisions.get(step.risk, Decision.BLOCK)
        # A unique fallback remains eligible. Historical health is not a kill switch.
        return PolicyResult(decision=decision, code=f"RISK_{decision.value}")
