"""Classify observed failures, not fault labels or the expected scenario outcome."""
from collections import Counter
from decimal import Decimal

from capability_health.aggregate import rate
from deterministic_ui.evidence import Event
from deterministic_ui.models import CapabilityArtifact, RunResult, Status
from .models import EvaluationRun, EvaluationSummary, FailureAnalysis, FailureCode as F, PageFacts
from tenant_reuse.models import digest


def classify(result: RunResult, artifact: CapabilityArtifact, facts: PageFacts,
             events: list[Event]) -> FailureAnalysis:
    failed_primary=any(e.kind=="locator_attempt" and e.strategy_index==0 and e.matches==0
                       and (e.condition_id is None or e.condition_id not in {o.condition.id for o in artifact.business_outcomes})
                       for e in events)
    findings=[F.PRIMARY_LOCATOR_FAILED] if failed_primary else []
    failure=result.failure
    if result.status in {Status.SUCCESS,Status.BUSINESS_OUTCOME}:
        return FailureAnalysis(findings=findings,evidence_refs=result.evidence_refs)
    code=F.ENGINE_FAILURE
    condition=failure.expected_condition if failure else None
    step=next((s for s in artifact.steps if failure and s.id==failure.step_id),None)
    if step and condition:
        if step.precondition and condition==step.precondition.id:
            findings.append(F.PRECONDITION_FAILED)
        elif step.postcondition and condition==step.postcondition.id:
            findings.append(F.POSTCONDITION_FAILED)
    if failure and failure.code=="AMBIGUOUS_TARGET":
        code=F.AMBIGUOUS_TARGET
    elif facts.loading or facts.unexpected_workspace or facts.identity_matches is False:
        code=F.PAGE_STATE_INVALID
        if facts.loading:
            findings.append(F.PARTIAL_PAGE_LOAD)
    elif result.status==Status.HUMAN_REQUIRED:
        code=F.POLICY_REVIEW_REQUIRED
    elif step and step.id==artifact.steps[0].id and not facts.expected_input_role_present:
        code=F.REQUIRED_ELEMENT_MISSING
    elif F.POSTCONDITION_FAILED in findings:
        code=F.POSTCONDITION_FAILED
    elif failure and (failure.code=="NO_TARGET" or (
        F.PRECONDITION_FAILED in findings and any(e.kind=="locator_attempt" and (e.strategy_index or 0)>0
                                                and e.step_id==failure.step_id and e.matches==0 for e in events))):
        code=F.FALLBACK_EXHAUSTED
    elif F.PRECONDITION_FAILED in findings:
        code=F.PRECONDITION_FAILED
    return FailureAnalysis(code=code,findings=findings,engine_code=failure.code if failure else None,
        step_id=failure.step_id if failure else None,condition_id=condition,evidence_refs=result.evidence_refs)


def summarize(artifact: CapabilityArtifact, runs: list[EvaluationRun]) -> EvaluationSummary:
    total=len(runs)
    metrics=[r.metrics for r in runs]
    successful=sum(r.status==Status.SUCCESS for r in metrics)
    business=sum(r.status==Status.BUSINESS_OUTCOME for r in metrics)
    attempts=sum(r.primary_locator_attempts for r in metrics)
    fallback_attempted=sum(r.fallback_attempted for r in runs)
    recovered=sum(r.fallback_recovered for r in runs)
    counts=Counter(r.analysis.code.value for r in runs if r.analysis.code)
    ordered=dict(sorted(counts.items(),key=lambda item:(-item[1],item[0])))
    return EvaluationSummary(capability_id=artifact.capability_id,capability_version=artifact.capability_version,
        canonical_digest=digest(artifact),total_runs=total,successful_runs=successful,business_outcomes=business,
        success_rate=rate(successful+business,total) or Decimal(0),
        primary_locator_success_rate=rate(sum(r.primary_locator_successes for r in metrics),attempts),
        fallback_usage_rate=rate(sum(r.fallback_locator_successes for r in metrics),attempts),
        fallback_recovery_rate=rate(recovered,fallback_attempted),fallback_attempted_runs=fallback_attempted,
        fallback_recovered_runs=recovered,
        unrecoverable_failure_rate=rate(sum(r.status in {Status.HARD_FAILURE,Status.RECOVERABLE_ERROR} for r in metrics),total) or Decimal(0),
        human_intervention_rate=rate(sum(r.status==Status.HUMAN_REQUIRED or r.human_handoff_count>0 for r in metrics),total) or Decimal(0),
        drift_event_count=sum(r.drift_signal_count for r in metrics),
        expectation_pass_rate=rate(sum(r.expectation_met for r in runs),total) or Decimal(0),
        failure_counts=ordered,most_common_failure=next(iter(ordered),None),
        model_calls=sum(r.model_calls for r in metrics),runs=runs)
