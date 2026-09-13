"""Scenario orchestration around the existing tenant replay and Surface abstractions."""
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
import json
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from capability_health.extract import extract_run
from deterministic_ui.evidence import Event
from deterministic_ui.models import Accessibility, CapabilityArtifact, SemanticTarget, Status
from deterministic_ui.resolver import LocatorResolver
from deterministic_ui.surface import Surface
from deterministic_ui.templates import render
from tenant_reuse.application import observe_application
from tenant_reuse.binder import TenantBindingResolver
from tenant_reuse.models import TenantBinding, TenantContext
from tenant_reuse.runner import replay_tenant
from .analysis import classify, summarize
from .models import EvaluationRun, EvaluationSummary, PageFacts, Scenario


class EvaluationRunner:
    def __init__(self, canonical: CapabilityArtifact, bindings: dict[str,TenantBinding],
                 base_url: str, surface_factory: Callable[[str],AbstractAsyncContextManager[Surface]], *,
                 evidence_root: Path=Path("evidence/evals")):
        self.canonical=canonical
        self.bindings=bindings
        self.base_url=base_url
        self.surface_factory=surface_factory
        self.evidence_root=evidence_root

    async def execute(self, scenarios: list[Scenario], *, repeats: int=1) -> tuple[EvaluationSummary,Path]:
        if not 1<=repeats<=20 or not scenarios:
            raise ValueError("BOUNDED_NONEMPTY_EVALUATION_REQUIRED")
        folder=self.evidence_root/uuid4().hex
        folder.mkdir(parents=True,exist_ok=False,mode=0o700)
        records=[]
        for scenario in scenarios:
            for _ in range(repeats):
                query=urlencode({"tenant":scenario.tenant_id,"drift":scenario.drift,"fault":scenario.fault})
                context=TenantContext(tenant_id=scenario.tenant_id,display_name=scenario.tenant_id,
                    base_url=f"{self.base_url}/?{query}",product=self.canonical.compatibility.application,
                    application_version=self.canonical.compatibility.application_version)
                binding=self.bindings[scenario.tenant_id]
                async with self.surface_factory(context.base_url) as surface:
                    result=await replay_tenant(self.canonical,context,binding,surface,
                        {"member_id":scenario.member_id},evidence_root=folder/"runs")
                    observation=await surface.observe()
                    effective=TenantBindingResolver().bind(self.canonical,context,binding,await observe_application(surface)).artifact
                    condition=effective.success
                    resolved=await LocatorResolver().resolve(condition.target,surface)
                    identity_matches=None
                    if resolved.succeeded and resolved.target is not None and condition.expected.kind=="text_equals":
                        displayed=await surface.observe(resolved.target)
                        assert condition.expected.value is not None
                        identity_matches=displayed.text==render(condition.expected.value,{"member_id":scenario.member_id})
                    expected_roles={s.role for s in effective.steps[0].target.strategies if s.type=="accessibility"}
                    unexpected=await LocatorResolver().resolve(SemanticTarget(
                        concept="unexpected_workspace",strategies=[Accessibility(role="region",name="Unexpected workspace")]),surface)
                    facts=PageFacts(expected_input_role_present=any(el.role in expected_roles for el in observation.elements),
                        loading=any(el.name=="Application loading" for el in observation.elements),
                        unexpected_workspace=unexpected.matches>0,
                        identity_matches=identity_matches)
                    await surface.release_targets()
                run_directory=folder/"runs"/result.run_id
                events=[Event.model_validate_json(line) for line in (run_directory/"events.jsonl").read_text().splitlines()]
                analysis=classify(result,effective,facts,events)
                metrics=extract_run(run_directory)
                business_conditions={outcome.condition.id for outcome in effective.business_outcomes}
                fallback_attempted=any(e.kind=="locator_attempt" and (e.strategy_index or 0)>0
                                       and e.condition_id not in business_conditions for e in events)
                output_verified=(result.outputs.get("savings_balance")==scenario.expected_balance
                                 if result.status==Status.SUCCESS else None)
                record=EvaluationRun(scenario=scenario,metrics=metrics,page_facts=facts,analysis=analysis,
                    fallback_attempted=fallback_attempted,
                    fallback_recovered=fallback_attempted and result.status in {Status.SUCCESS,Status.BUSINESS_OUTCOME},
                    expectation_met=(result.status==scenario.expected_status and analysis.code==scenario.expected_failure
                                     and output_verified is not False),
                    output_verified=output_verified)
                records.append(record)
                with (folder/"results.jsonl").open("a") as stream:
                    (folder/"results.jsonl").chmod(0o600)
                    stream.write(record.model_dump_json()+"\n")
        summary=summarize(self.canonical,records)
        (folder/"summary.json").write_text(summary.model_dump_json(indent=2)+"\n")
        (folder/"summary.json").chmod(0o600)
        (folder/"methodology.json").write_text(json.dumps({
            "scenarios":[s.model_dump(mode="json") for s in scenarios],"repeats":repeats,
            "locator_denominator":"action-target resolutions only; excludes polling/business probes",
            "success_denominator":"all completed runs; SUCCESS and valid BUSINESS_OUTCOME count as completion",
            "fallback_recovery_denominator":"runs with an attempted non-business fallback",
            "unrecoverable":"terminal HARD_FAILURE or RECOVERABLE_ERROR after bounded recovery",
            "human_intervention":"HUMAN_REQUIRED or recorded handoff",
            "failure_classification":"engine evidence and redacted observed page facts; not injected scenario names",
        },indent=2)+"\n")
        lines=["# Automated evaluation and failure analysis","",
               f"Canonical capability: {summary.capability_id}@{summary.capability_version}","",
               "[Summary and metrics](summary.json) · [Methodology](methodology.json) · [Per-run records](results.jsonl)","",
               "| Scenario | Actual status | Failure classification | Expectation met | Run |",
               "|---|---|---|---|---|"]
        for record in records:
            lines.append(f"| {record.scenario.id} | {record.metrics.status} | {record.analysis.code or 'none'} | {record.expectation_met} | [{record.metrics.run_id}](runs/{record.metrics.run_id}/result.json) |")
        (folder/"README.md").write_text("\n".join(lines)+"\n")
        return summary,folder
