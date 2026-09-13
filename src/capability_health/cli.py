import argparse
from pathlib import Path

from .aggregate import HealthAggregator
from .extract import load_runs
from .models import CapabilityHealth, Thresholds
from .store import HealthStore


def percentage(value):
    return f"{value*100:.1f}%" if value is not None else "unavailable"


def format_health(summary: CapabilityHealth) -> str:
    lines=[f"Capability: {summary.capability_id}@{summary.capability_version}",
        f"Overall: {summary.status}",
        f"Runs: {summary.total_runs} | Reliable completion: {percentage(summary.success_rate)}",
        f"Primary locator: {percentage(summary.primary_locator_match_rate)} | Fallback: {percentage(summary.fallback_rate)}",
        f"Human intervention: {percentage(summary.human_intervention_rate)} | Model calls: {summary.model_calls}",
        "Tenants:"]
    for tenant in summary.tenant_health:
        lines.append(f"  {tenant.tenant_id}: {tenant.status}; completion={percentage(tenant.success_rate)}; fallback={percentage(tenant.fallback_rate)}")
        if tenant.reasons:
            lines.append("    "+", ".join(reason.code for reason in tenant.reasons))
    if summary.evidence_issues:
        lines.append(f"Excluded evidence bundles: {len(summary.evidence_issues)} (see JSON reasons)")
    lines.append("Recommendation: "+summary.recommendation)
    return "\n".join(lines)


def main():
    parser=argparse.ArgumentParser(description="Recompute capability health from structured replay evidence")
    parser.add_argument("--capability",default="get_member_balance")
    parser.add_argument("--version",default="1.0.0")
    parser.add_argument("--evidence",type=Path,default=Path("evidence/tenants"))
    parser.add_argument("--store",type=Path,default=Path("health"))
    parser.add_argument("--thresholds",type=Path)
    args=parser.parse_args()
    thresholds=Thresholds.model_validate_json(args.thresholds.read_text()) if args.thresholds else Thresholds()
    runs,issues=load_runs(args.evidence,args.capability,args.version)
    summary=HealthAggregator(thresholds).aggregate(args.capability,args.version,runs,issues=issues)
    saved=HealthStore(args.store).save(summary,runs)
    print(format_health(summary))
    print(f"Derived summary: {saved}/summary.json")


if __name__=="__main__":
    main()
