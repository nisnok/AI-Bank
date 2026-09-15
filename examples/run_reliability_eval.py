"""Genuine bounded browser runs demonstrating success with declining locator reliability."""
if __name__ == "__main__":
    from acceptance.command import managed_main
    managed_main("multitenant")

from acceptance.bundle import output_root

# Install the existing replay import guard before importing any application modules.
from replay_tenant import BLOCKED
import argparse
import asyncio
from decimal import Decimal
import json
from pathlib import Path
import sys
from uuid import uuid4

from bank_simulator.server import running_server
from capability_health.aggregate import HealthAggregator
from capability_health.cli import format_health
from capability_health.extract import load_runs
from capability_health.models import HealthStatus, Thresholds
from capability_health.store import HealthStore
from deterministic_ui.models import CapabilityArtifact, Status
from deterministic_ui.playwright_surface import PlaywrightSurface
from tenant_reuse.models import TenantBinding, TenantContext, digest
from tenant_reuse.runner import replay_tenant


async def run(args):
    canonical_path=Path("capabilities/generated/get_member_balance/1.0.0/validated.json")
    original=canonical_path.read_bytes()
    canonical=CapabilityArtifact.model_validate_json(original)
    bindings={tenant:TenantBinding.model_validate_json(Path(f"tenant_bindings/{tenant}/1.0.0.json").read_text())
              for tenant in ("bank_a","bank_b")}
    evaluation=args.evidence_root/uuid4().hex
    evaluation.mkdir(parents=True,exist_ok=False)
    thresholds=Thresholds()
    snapshots=[]
    manifest=[]
    with running_server() as server:
        async def execute(tenant_id,drift="none",version="1"):
            ctx=TenantContext(tenant_id=tenant_id,display_name=tenant_id,
                base_url=f"{server.url}/?tenant={tenant_id}&drift={drift}&application_version={version}",
                product="legacy-bank-simulator",application_version="1")
            async with PlaywrightSurface.open(ctx.base_url) as surface:
                result=await replay_tenant(canonical,ctx,bindings[tenant_id],surface,{"member_id":"83921"},
                                           evidence_root=evaluation/"runs")
            expected=Status.HARD_FAILURE if version!="1" else Status.HUMAN_REQUIRED if drift=="ambiguous" else Status.SUCCESS
            if result.status!=expected:
                raise RuntimeError("UNEXPECTED_EVALUATION_RESULT")
            if expected==Status.SUCCESS and result.outputs!={"savings_balance":Decimal("807.20")}:
                raise RuntimeError("BALANCE_NOT_VERIFIED")
            manifest.append({"run_id":result.run_id,"tenant_id":tenant_id,"drift":drift,
                             "application_version":version,"status":result.status,"model_calls":result.model_calls})
            print(f"Run {len(manifest)}: {tenant_id}/{drift} -> {result.status}; model_calls=0",flush=True)

        def snapshot(stage,expected):
            metrics,issues=load_runs(evaluation/"runs",canonical.capability_id,canonical.capability_version)
            if issues:
                raise RuntimeError("EVALUATION_EVIDENCE_INVALID")
            summary=HealthAggregator(thresholds).aggregate(canonical.capability_id,canonical.capability_version,metrics)
            states={tenant.tenant_id:tenant.status for tenant in summary.tenant_health}
            if any(states.get(tenant)!=status for tenant,status in expected.items()):
                raise RuntimeError("UNEXPECTED_HEALTH_ASSESSMENT")
            saved=HealthStore(evaluation/"derived"/stage).save(summary,metrics)
            snapshots.append({"stage":stage,"summary":str(saved/"summary.json")})
            print(f"\n{stage}\n{format_health(summary)}\nSummary: {saved}/summary.json\n",flush=True)

        for _ in range(5):
            await execute("bank_a")
        snapshot("bank_a_baseline",{"bank_a":HealthStatus.HEALTHY})
        for _ in range(5):
            await execute("bank_b")
        snapshot("both_baseline",{"bank_a":HealthStatus.HEALTHY,"bank_b":HealthStatus.HEALTHY})
        for _ in range(5):
            await execute("bank_b","label")
        snapshot("successful_drift",{"bank_a":HealthStatus.HEALTHY,"bank_b":HealthStatus.DEGRADED})
        if args.include_failures:
            for _ in range(3):
                await execute("bank_b","ambiguous")
            for _ in range(3):
                await execute("bank_b",version="2")
            snapshot("faults",{"bank_a":HealthStatus.HEALTHY,"bank_b":HealthStatus.UNHEALTHY})
    if any(name.partition(".")[0] in BLOCKED for name in sys.modules):
        raise RuntimeError("MODEL_IMPORT_DETECTED")
    assert canonical_path.read_bytes()==original
    report={"canonical_digest":digest(canonical),"canonical_unchanged":True,
            "model_import_guard":"enabled","loaded_model_modules":[],
            "model_calls":0,"runs":manifest,"snapshots":snapshots}
    (evaluation/"evaluation.json").write_text(json.dumps(report,indent=2)+"\n")
    lines=["# Capability health evaluation","",
           "Actual Chromium/simulator replay. All baseline and label-drift runs succeeded.",
           "Bank B then became DEGRADED from measured locator fallback usage; Bank A stayed HEALTHY.","",
           "## Derived snapshots",""]
    for item in snapshots:
        relative=Path(item["summary"]).relative_to(evaluation)
        lines.append(f"- [{item['stage']}]({relative}): summary, run metrics, thresholds, and source evidence digests.")
    lines.extend(["","Source run IDs and scenario configuration: [evaluation.json](evaluation.json).",
                  "Original replay evidence lives under runs/<run_id>/. Derived runs.jsonl links each source directory.",
                  "No capability or binding was rewritten. No model calls were used."])
    (evaluation/"README.md").write_text("\n".join(lines)+"\n")
    print(f"Reviewer index: {evaluation}/README.md")
    return 0


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=output_root("multitenant", "health"))
    parser.add_argument("--include-failures",action="store_true",help="Add six genuine ambiguity/incompatibility runs")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
