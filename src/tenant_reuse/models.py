from hashlib import sha256
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from deterministic_ui.models import Accessibility, CapabilityArtifact, Model, Relative, SemanticTarget, Strategy

def digest(artifact: CapabilityArtifact) -> str:
    return sha256(artifact.model_dump_json().encode()).hexdigest()


class TenantContext(Model):
    tenant_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str
    base_url: str
    product: str
    application_version: str

    @field_validator("base_url")
    @classmethod
    def local_url(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username or parsed.password or parsed.fragment):
            raise ValueError("LOCAL_SIMULATOR_URL_REQUIRED")
        return value


class ObservedApplication(Model):
    tenant_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    product: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,127}$")
    application_version: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+){0,3}$", max_length=32)


class TargetBinding(Model):
    # Match the entire canonical target: observation-local concepts are not unique.
    canonical_target: SemanticTarget
    strategies: list[Strategy] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def valid_ladder(self):
        SemanticTarget(concept=self.canonical_target.concept, strategies=self.strategies)
        order = {"accessibility":0, "label":1, "text":2, "relative":3, "css":4}
        ranks = [order[strategy.type] for strategy in self.strategies]
        if ranks != sorted(ranks) or len({s.model_dump_json() for s in self.strategies}) != len(self.strategies):
            raise ValueError("INVALID_BINDING_LADDER")
        roles = {s.role for s in self.canonical_target.strategies if isinstance(s, (Accessibility, Relative))}
        if roles and any(s.role not in roles for s in self.strategies if isinstance(s, (Accessibility, Relative))):
            raise ValueError("BINDING_CANNOT_CHANGE_TARGET_ROLE")
        if any(s.type != "css" for s in self.canonical_target.strategies) and all(s.type == "css" for s in self.strategies):
            raise ValueError("SEMANTIC_STRATEGY_REQUIRED")
        return self


class TenantBinding(Model):
    tenant_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    binding_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    capability_id: str
    capability_version: str
    canonical_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    product: str
    application_version: str
    targets: list[TargetBinding] = Field(default_factory=list)


class EffectiveCapability(Model):
    artifact: CapabilityArtifact
    tenant: TenantContext
    binding_version: str
    canonical_digest: str
    binding_digest: str
    observed_application: ObservedApplication
