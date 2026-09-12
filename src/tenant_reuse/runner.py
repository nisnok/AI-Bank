"""Compatibility preflight and binding before the unchanged deterministic engine."""
from pathlib import Path
from uuid import uuid4

from deterministic_ui.evidence import EvidenceContext, EvidenceWriter
from deterministic_ui.models import CapabilityArtifact, Failure, RunResult, Status
from deterministic_ui.replay import ReplayEngine
from deterministic_ui.surface import Surface, SurfaceError
from .application import observe_application
from .binder import BindingError, TenantBindingResolver
from .models import TenantBinding, TenantContext, digest


async def replay_tenant(canonical: CapabilityArtifact, tenant: TenantContext, binding: TenantBinding | None,
                        surface: Surface, inputs: dict[str, object], *,
                        evidence_root: Path = Path("evidence/tenants")) -> RunResult:
    context = EvidenceContext(tenant_id=tenant.tenant_id,
        binding_version=binding.binding_version if binding else None,
        canonical_digest=digest(canonical), product=tenant.product)
    try:
        observed = await observe_application(surface)
        context = context.model_copy(update={"observed_application_version":observed.application_version,
                                             "observed_product":observed.product,
                                             "observed_tenant_id":observed.tenant_id})
        effective = TenantBindingResolver().bind(canonical, tenant, binding, observed)
    except (BindingError, SurfaceError) as error:
        code = str(error) if isinstance(error, BindingError) else "APPLICATION_IDENTITY_UNAVAILABLE"
        run_id = uuid4().hex
        writer = EvidenceWriter(evidence_root, run_id, canonical, context=context)
        refs = [str(writer.directory / name) for name in ("metadata.json","events.jsonl","result.json")]
        result = RunResult(run_id=run_id, status=Status.HARD_FAILURE, evidence_refs=refs,
            failure=Failure(run_id=run_id, code=code, evidence_refs=refs,
                            safe_next_action="Review tenant binding and application compatibility before execution"))
        writer.emit("compatibility_rejected", status=code)
        writer.finish(result)
        return result
    context = context.model_copy(update={"binding_digest":effective.binding_digest,
        "observed_application_version":effective.observed_application.application_version})
    return await ReplayEngine(surface, evidence_root=evidence_root, evidence_context=context).execute(
        effective.artifact, inputs)
