"""Execute controlled browser faults and classify their genuine evidence."""
if __name__ == "__main__":
    from acceptance.command import managed_main
    managed_main("evaluation")

from acceptance.bundle import output_root

from replay_tenant import BLOCKED
import argparse
import asyncio
from pathlib import Path
import sys

from bank_simulator.server import running_server
from capability_eval.runner import EvaluationRunner
from capability_eval.scenarios import SCENARIOS
from capability_health.cli import percentage
from deterministic_ui.models import CapabilityArtifact
from deterministic_ui.playwright_surface import PlaywrightSurface
from tenant_reuse.models import TenantBinding


async def run(args):
    path=Path("capabilities/generated/get_member_balance/1.0.0/validated.json")
    original=path.read_bytes()
    canonical=CapabilityArtifact.model_validate_json(original)
    bindings={tenant:TenantBinding.model_validate_json(Path(f"tenant_bindings/{tenant}/1.0.0.json").read_text())
              for tenant in ("bank_a","bank_b")}
    selected=[s for s in SCENARIOS if args.scenario is None or s.id==args.scenario]
    with running_server() as server:
        runner=EvaluationRunner(canonical,bindings,server.url,PlaywrightSurface.open, evidence_root=args.evidence_root)
        summary,folder=await runner.execute(selected,repeats=args.repeats)
    if any(name.partition(".")[0] in BLOCKED for name in sys.modules):
        raise RuntimeError("MODEL_IMPORT_DETECTED")
    assert original==path.read_bytes()
    print(f"{summary.capability_id}@{summary.capability_version}\n")
    print(f"Runs: {summary.total_runs}")
    print(f"Success rate (valid business outcomes included): {percentage(summary.success_rate)}")
    print(f"Primary locator: {percentage(summary.primary_locator_success_rate)}")
    print(f"Fallback usage: {percentage(summary.fallback_usage_rate)}")
    print(f"Fallback recovery: {percentage(summary.fallback_recovery_rate)}")
    print(f"Unrecoverable: {percentage(summary.unrecoverable_failure_rate)}")
    print(f"Human intervention: {percentage(summary.human_intervention_rate)}")
    print(f"Drift events: {summary.drift_event_count}")
    print(f"Scenario expectations passed: {percentage(summary.expectation_pass_rate)}")
    print(f"Most common failure: {summary.most_common_failure or 'none'}")
    print(f"Model calls: {summary.model_calls}\nEvidence: {folder}/README.md")
    return 0 if all(run.expectation_met for run in summary.runs) else 1


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=output_root("evaluation", "evals"))
    parser.add_argument("--repeats",type=int,default=1)
    parser.add_argument("--scenario",choices=[s.id for s in SCENARIOS])
    raise SystemExit(asyncio.run(run(parser.parse_args())))
