import ast
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from capability_health.aggregate import HealthAggregator
from capability_health.extract import EvidenceError, extract_run, load_runs
from capability_health.models import HealthStatus as H, RunMetrics, Thresholds
from capability_health.policy import ReliabilityPolicy
from capability_health.store import HealthStore
from deterministic_ui.evidence import EvidenceContext
from deterministic_ui.models import Decision, Risk, Status
from deterministic_ui.policy import PolicyConfig
from deterministic_ui.replay import ReplayEngine
from deterministic_ui.resolver import LocatorResolver


def metric(index,tenant="bank_a",**changes):
    started=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=index)
    data=dict(run_id=f"run_{index}",capability_id="get_member_balance",capability_version="1.0.0",
        tenant_id=tenant,started_at=started,completed_at=started+timedelta(seconds=1),
        status=Status.SUCCESS,duration_ms=Decimal(100),step_count=3,
        primary_locator_attempts=3,primary_locator_successes=3,
        evidence_directory=f"evidence/test/run_{index}",evidence_digest="unit-fixture")
    return RunMetrics.model_validate(data|changes)


def aggregate(runs,thresholds=None):
    return HealthAggregator(thresholds).aggregate("get_member_balance","1.0.0",runs)


def codes(summary):
    return {reason.code for reason in summary.reasons}


def test_insufficient_data():
    summary=aggregate([metric(0)])
    assert summary.status==H.INSUFFICIENT_DATA and "MINIMUM_RUNS_NOT_MET" in codes(summary)


def test_clean_runs_healthy():
    summary=aggregate([metric(i) for i in range(5)])
    assert summary.status==H.HEALTHY and not summary.reasons
    assert summary.success_rate==1 and summary.primary_locator_match_rate==1
    assert summary.fallback_rate==0 and summary.p95_latency_ms==100


def test_successful_fallback_and_increasing_trend():
    clean=[metric(i,"bank_b") for i in range(5)]
    fragile=[metric(i,"bank_b",primary_locator_successes=2,fallback_locator_successes=1,
                    maximum_fallback_depth=2,drift_signal_count=3) for i in range(5,10)]
    summary=aggregate(clean+fragile)
    tenant=summary.tenant_health[0]
    assert summary.success_rate==1 and summary.status==H.DEGRADED
    assert {"FALLBACK_USAGE_HIGH","FALLBACK_USAGE_INCREASING"}<=codes(tenant)
    assert tenant.fallback_rate==Decimal(".1667")
    assert tenant.recent_run_ids==[f"run_{i}" for i in range(5,10)]
    assert tenant.historical_run_ids==[f"run_{i}" for i in range(5)]


@pytest.mark.parametrize("status,extra,reason", [
    (Status.HARD_FAILURE,{},"REPEATED_HARD_FAILURES"),
    (Status.HUMAN_REQUIRED,{"ambiguity_count":1},"REPEATED_AMBIGUITY")])
def test_repeated_failures_unhealthy(status,extra,reason):
    runs=[metric(i,status=status,**extra) if i<2 else metric(i) for i in range(5)]
    summary=aggregate(runs)
    assert summary.status==H.UNHEALTHY and reason in codes(summary.tenant_health[0])


def test_business_outcomes_count_as_correct_execution():
    summary=aggregate([metric(i,status=Status.BUSINESS_OUTCOME) for i in range(5)])
    assert summary.status==H.HEALTHY and summary.success_rate==1
    assert summary.successful_runs==0 and summary.business_outcomes==5 and summary.hard_failure_rate==0


def test_recovery_and_handoff_are_distinct_from_hard_failure():
    runs=[metric(i,recoverable_error_count=1,recovery_attempts=1,successful_recovery_count=1,
                 human_handoff_count=1,human_action_count=2) for i in range(5)]
    summary=aggregate(runs)
    assert summary.status==H.DEGRADED and summary.success_rate==1
    assert summary.recovery_rate==summary.human_intervention_rate==1
    assert summary.successful_recoveries==5 and summary.hard_failures==0


def test_per_tenant_health_not_hidden_by_global_average():
    runs=[metric(i) for i in range(30)]
    runs += [metric(i,"bank_b",primary_locator_successes=2,fallback_locator_successes=1) for i in range(30,35)]
    summary=aggregate(runs)
    tenants={tenant.tenant_id:tenant for tenant in summary.tenant_health}
    assert summary.fallback_rate is not None
    assert summary.fallback_rate<Decimal(".10")
    assert tenants["bank_a"].status==H.HEALTHY and tenants["bank_b"].status==H.DEGRADED
    assert summary.status==H.DEGRADED
    assert any(reason.code=="TENANT_DEGRADED" and reason.tenant_id=="bank_b" for reason in summary.reasons)


def test_thresholds_and_window_minimum_are_honored():
    runs=[metric(i,primary_locator_successes=2,fallback_locator_successes=1) for i in range(5)]
    relaxed=Thresholds(maximum_fallback_rate=Decimal(".5"),minimum_primary_rate=Decimal(".5"))
    assert aggregate(runs,relaxed).status==H.HEALTHY
    assert "FALLBACK_USAGE_INCREASING" not in codes(aggregate(runs).tenant_health[0])
    assert aggregate(runs,Thresholds(minimum_runs=6)).status==H.INSUFFICIENT_DATA


def test_latency_trend_and_nearest_rank_p95():
    runs=[metric(i,duration_ms=Decimal(100 if i<5 else 400)) for i in range(10)]
    summary=aggregate(runs)
    assert summary.p95_latency_ms==400 and summary.average_latency_ms==250
    assert "LATENCY_REGRESSION" in codes(summary.tenant_health[0])


async def test_real_evidence_extraction_deterministic_and_recovery(artifact,surface,tmp_path):
    surface.fail_fills=1
    result=await ReplayEngine(surface,evidence_root=tmp_path,
        evidence_context=EvidenceContext(tenant_id="bank_a",binding_version="1.0.0",purpose="VALIDATION")).execute(
            artifact,{"member_id":"sensitive-runtime-fixture"})
    first=extract_run(tmp_path/result.run_id)
    assert first==extract_run(tmp_path/result.run_id)
    assert first.status==Status.SUCCESS and first.validation_outcome==Status.SUCCESS
    assert first.recovery_attempts==1 and first.successful_recovery_count==1
    assert first.primary_locator_attempts==4  # Failed fill, successful fill, search, extract.
    assert first.primary_locator_successes==4 and first.ambiguity_count==0
    assert "sensitive-runtime-fixture" not in first.model_dump_json()
    assert first.duration_ms is not None and first.evidence_digest


async def test_malformed_incomplete_and_mismatched_evidence(artifact,surface,tmp_path):
    result=await ReplayEngine(surface,evidence_root=tmp_path).execute(artifact,{"member_id":"sensitive-runtime-fixture"})
    folder=tmp_path/result.run_id
    original=(folder/"result.json").read_text()
    (folder/"result.json").write_text("{")
    with pytest.raises(EvidenceError):
        extract_run(folder)
    runs,issues=load_runs(tmp_path,artifact.capability_id,artifact.capability_version)
    assert not runs and len(issues)==1
    summary=HealthAggregator().aggregate(artifact.capability_id,artifact.capability_version,runs,issues=issues)
    assert "EVIDENCE_EXCLUDED" in codes(summary)
    (folder/"result.json").write_text(original)
    events=(folder/"events.jsonl").read_text().splitlines()
    (folder/"events.jsonl").write_text("\n".join(line for line in events if '"run_finished"' not in line)+"\n")
    with pytest.raises(EvidenceError,match="TERMINAL_EVENT_MISSING"):
        extract_run(folder)


def test_derived_store_and_artifact_unchanged(tmp_path):
    artifact=Path("capabilities/generated/get_member_balance/1.0.0/validated.json")
    before=artifact.read_bytes()
    runs=[metric(i) for i in range(5)]
    summary=aggregate(runs)
    first=HealthStore(tmp_path).save(summary,runs)
    second=HealthStore(tmp_path).save(summary,runs)
    assert first!=second and artifact.read_bytes()==before
    assert json.loads((first/"summary.json").read_text())["derived_data"]
    assert len((first/"runs.jsonl").read_text().splitlines())==5


@pytest.mark.parametrize("risk,configured,expected", [
    (Risk.READ,Decision.ALLOW,Decision.ALLOW),
    (Risk.IRREVERSIBLE,Decision.ALLOW,Decision.REQUIRE_HUMAN),
    (Risk.IRREVERSIBLE,Decision.BLOCK,Decision.BLOCK)])
async def test_risk_aware_policy_only_strengthens(artifact,surface,risk,configured,expected):
    summary=aggregate([metric(i,primary_locator_successes=2,fallback_locator_successes=1) for i in range(5)])
    artifact=artifact.model_copy(update={"safety":artifact.safety.model_copy(update={"max_risk":Risk.IRREVERSIBLE})})
    step=artifact.steps[1].model_copy(update={"risk":risk})
    resolved=await LocatorResolver().resolve(step.target,surface)
    policy=ReliabilityPolicy(summary,"bank_a",PolicyConfig(decisions={risk:configured}))
    assert policy.evaluate(artifact,step,resolved).decision==expected


def test_health_has_no_model_or_browser_dependencies():
    for path in Path("src/capability_health").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            modules=[a.name for a in node.names] if isinstance(node,ast.Import) else (
                [node.module or ""] if isinstance(node,ast.ImportFrom) else [])
            assert not any(module.split(".")[0] in {"discovery","playwright","google","openai","anthropic"} for module in modules)
    assert "capability_health" not in Path("src/deterministic_ui/replay.py").read_text()
