"""Optional policy adapter: historical evidence can strengthen, never weaken, a decision."""
from deterministic_ui.models import Decision, Risk
from deterministic_ui.policy import PolicyEngine, PolicyResult
from .models import CapabilityHealth, HealthStatus


class ReliabilityPolicy(PolicyEngine):
    def __init__(self, assessment: CapabilityHealth, tenant_id: str, config=None, *,
                 require_human_for_irreversible: bool=True):
        super().__init__(config)
        self.assessment=assessment
        self.tenant=next((tenant for tenant in assessment.tenant_health if tenant.tenant_id==tenant_id),None)
        if self.tenant is None:
            raise ValueError("TENANT_HEALTH_MISSING")
        self.require_human_for_irreversible=require_human_for_irreversible

    def evaluate(self, artifact, step, resolution):
        base=super().evaluate(artifact,step,resolution)
        if base.decision!=Decision.ALLOW:
            return base
        if (artifact.capability_id,artifact.capability_version)!=(self.assessment.capability_id,self.assessment.capability_version):
            return PolicyResult(decision=Decision.BLOCK,code="HEALTH_CONTEXT_MISMATCH")
        if (self.require_human_for_irreversible and step.risk==Risk.IRREVERSIBLE
            and self.tenant is not None and self.tenant.status in {HealthStatus.DEGRADED,HealthStatus.UNHEALTHY}):
            return PolicyResult(decision=Decision.REQUIRE_HUMAN,code="HISTORICAL_RELIABILITY_REVIEW")
        return base
