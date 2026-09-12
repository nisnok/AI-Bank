"""Strict locator substitution, with no workflow/policy/model/browser dependency."""
from hashlib import sha256

from deterministic_ui.models import CapabilityArtifact
from .models import EffectiveCapability, ObservedApplication, TenantBinding, TenantContext, digest


class BindingError(ValueError):
    """Fixed safe error codes only."""


class TenantBindingResolver:
    def bind(self, canonical: CapabilityArtifact, tenant: TenantContext,
             binding: TenantBinding | None, observed: ObservedApplication) -> EffectiveCapability:
        if binding is None:
            raise BindingError("TENANT_BINDING_REQUIRED")
        # Revalidate even when a Python caller constructed data with model_copy/model_construct.
        canonical = CapabilityArtifact.model_validate(canonical.model_dump())
        binding = TenantBinding.model_validate(binding.model_dump())
        if binding.tenant_id != tenant.tenant_id or observed.tenant_id != tenant.tenant_id:
            raise BindingError("TENANT_MISMATCH")
        if (binding.capability_id, binding.capability_version, binding.canonical_digest) != (
            canonical.capability_id, canonical.capability_version, digest(canonical)):
            raise BindingError("CANONICAL_BINDING_MISMATCH")
        if any(product != canonical.compatibility.application for product in
               (tenant.product, binding.product, observed.product)):
            raise BindingError("INCOMPATIBLE_PRODUCT")
        if any(version != canonical.compatibility.application_version for version in
               (tenant.application_version, binding.application_version, observed.application_version)):
            raise BindingError("INCOMPATIBLE_APPLICATION_VERSION")

        if any(strategy.type not in canonical.compatibility.required_features
               for target in binding.targets for strategy in target.strategies):
            raise BindingError("UNDECLARED_BINDING_FEATURE")
        source = canonical.model_dump(mode="json")
        matches = [0 for _ in binding.targets]
        keys = [target.canonical_target.model_dump_json() for target in binding.targets]
        if len(keys) != len(set(keys)):
            raise BindingError("DUPLICATE_TARGET_BINDING")

        def rewrite(value):
            if isinstance(value, list):
                return [rewrite(item) for item in value]
            if not isinstance(value, dict):
                return value
            result = {}
            for key, child in value.items():
                if key == "target" and isinstance(child, dict):
                    result[key] = child
                    for index, override in enumerate(binding.targets):
                        if child == override.canonical_target.model_dump(mode="json"):
                            result[key] = {**child, "strategies":[s.model_dump(mode="json") for s in override.strategies]}
                            matches[index] += 1
                else:
                    result[key] = rewrite(child)
            return result

        rewritten = rewrite(source)
        if any(count == 0 for count in matches):
            raise BindingError("UNKNOWN_CANONICAL_TARGET")

        def protected(value):
            if isinstance(value, list):
                return [protected(item) for item in value]
            if not isinstance(value, dict):
                return value
            return {key: ({"concept": child["concept"]} if key == "target" else protected(child))
                    for key, child in value.items()}

        if protected(source) != protected(rewritten):
            raise BindingError("PROTECTED_SEMANTICS_CHANGED")
        effective = CapabilityArtifact.model_validate(rewritten)
        return EffectiveCapability(artifact=effective, tenant=tenant,
            binding_version=binding.binding_version, canonical_digest=digest(canonical),
            binding_digest=sha256(binding.model_dump_json().encode()).hexdigest(),
            observed_application=observed)
