"""Deterministic counts, rates, bounded trends, and explainable demo thresholds."""
from datetime import datetime, timezone
from collections.abc import Sequence
from decimal import Decimal, ROUND_HALF_UP

from .models import (Assessment, CapabilityHealth, EvidenceIssue, HealthReason, HealthStatus,
                     RunMetrics, TenantHealth, Thresholds)
from deterministic_ui.models import Status


def rate(numerator: int, denominator: int) -> Decimal | None:
    return (Decimal(numerator)/Decimal(denominator)).quantize(Decimal(".0001"), rounding=ROUND_HALF_UP) if denominator else None


def mean(values: Sequence[Decimal | None]) -> Decimal | None:
    present=[value for value in values if value is not None]
    return (sum(present,Decimal(0))/len(present)).quantize(Decimal(".001"),rounding=ROUND_HALF_UP) if present else None


class HealthAggregator:
    def __init__(self, thresholds: Thresholds | None=None):
        self.thresholds=thresholds or Thresholds()

    def _assess(self, runs: list[RunMetrics], *, trends: bool=True) -> Assessment:
        t=self.thresholds
        runs=sorted(runs,key=lambda r:(r.completed_at,r.run_id))
        total=len(runs)
        success=sum(r.status==Status.SUCCESS for r in runs)
        business=sum(r.status==Status.BUSINESS_OUTCOME for r in runs)
        hard=sum(r.status==Status.HARD_FAILURE for r in runs)
        human=sum(r.status==Status.HUMAN_REQUIRED for r in runs)
        primary=sum(r.primary_locator_successes for r in runs)
        attempts=sum(r.primary_locator_attempts for r in runs)
        fallback=sum(r.fallback_locator_successes for r in runs)
        ambiguity_runs=sum(r.ambiguity_count>0 for r in runs)
        recovered_runs=sum(r.recovery_attempts>0 for r in runs)
        intervention=sum(r.human_handoff_count>0 or r.human_action_count>0 or r.status==Status.HUMAN_REQUIRED for r in runs)
        latencies=sorted(r.duration_ms for r in runs if r.duration_ms is not None)
        values=Assessment(total_runs=total, successful_runs=success, business_outcomes=business,
            hard_failures=hard, human_required_runs=human,
            success_rate=rate(success+business,total) or Decimal(0),
            primary_locator_match_rate=rate(primary,attempts), fallback_rate=rate(fallback,attempts),
            primary_locator_attempts=attempts, primary_locator_successes=primary, fallback_locator_successes=fallback,
            maximum_fallback_depth=max((r.maximum_fallback_depth for r in runs),default=0),
            recovery_attempts=sum(r.recovery_attempts for r in runs),
            recoverable_errors=sum(r.recoverable_error_count for r in runs),
            successful_recoveries=sum(r.successful_recovery_count for r in runs),
            recovery_rate=rate(recovered_runs,total) or Decimal(0),
            human_handoff_count=sum(r.human_handoff_count for r in runs),
            human_action_count=sum(r.human_action_count for r in runs),
            human_intervention_rate=rate(intervention,total) or Decimal(0),
            ambiguity_count=sum(r.ambiguity_count for r in runs),
            ambiguity_rate=rate(ambiguity_runs,total) or Decimal(0),
            hard_failure_rate=rate(hard,total) or Decimal(0),
            drift_signal_count=sum(r.drift_signal_count for r in runs),
            drift_rate=rate(sum(r.drift_signal_count>0 for r in runs),total) or Decimal(0),
            average_latency_ms=mean(latencies),
            p95_latency_ms=latencies[(95*len(latencies)+99)//100-1] if latencies else None,
            latency_samples=len(latencies),
            validation_runs=sum(r.validation_outcome is not None for r in runs),
            validation_successes=sum(r.validation_outcome==Status.SUCCESS for r in runs),
            model_calls=sum(r.model_calls for r in runs),
            binding_versions=sorted({r.binding_version for r in runs if r.binding_version}),
            run_ids=[r.run_id for r in runs],status=HealthStatus.HEALTHY,reasons=[],recommendation="")
        reasons=[]
        status=HealthStatus.HEALTHY
        def reason(code,metric,observed=None,threshold=None):
            reasons.append(HealthReason(code=code,metric=metric,observed=observed,threshold=threshold))
        if total<t.minimum_runs:
            status=HealthStatus.INSUFFICIENT_DATA
            reason("MINIMUM_RUNS_NOT_MET","total_runs",Decimal(total),Decimal(t.minimum_runs))
        else:
            if values.fallback_rate is not None and values.fallback_rate>t.maximum_fallback_rate:
                reason("FALLBACK_USAGE_HIGH","fallback_rate",values.fallback_rate,t.maximum_fallback_rate)
            if values.primary_locator_match_rate is not None and values.primary_locator_match_rate<t.minimum_primary_rate:
                reason("PRIMARY_LOCATOR_MATCH_RATE_LOW","primary_locator_match_rate",values.primary_locator_match_rate,t.minimum_primary_rate)
            if values.recovery_rate>t.maximum_recovery_rate:
                reason("RECOVERY_USAGE_HIGH","recovery_rate",values.recovery_rate,t.maximum_recovery_rate)
            if values.human_intervention_rate>t.maximum_intervention_rate:
                reason("HUMAN_INTERVENTION_HIGH","human_intervention_rate",values.human_intervention_rate,t.maximum_intervention_rate)
            if values.drift_signal_count:
                reason("LOCATOR_DRIFT_OBSERVED","drift_rate",values.drift_rate)
            if ambiguity_runs:
                reason("AMBIGUITY_OBSERVED","ambiguity_rate",values.ambiguity_rate)
            if hard:
                reason("HARD_FAILURES_OBSERVED","hard_failure_rate",values.hard_failure_rate)
            if any(r.status==Status.RECOVERABLE_ERROR for r in runs):
                reason("RECOVERY_EXHAUSTED","success_rate",values.success_rate)
            if reasons:
                status=HealthStatus.DEGRADED
            if hard>=t.minimum_repeated_failures and values.hard_failure_rate>=t.unhealthy_failure_rate:
                status=HealthStatus.UNHEALTHY
                reason("REPEATED_HARD_FAILURES","hard_failure_rate",values.hard_failure_rate,t.unhealthy_failure_rate)
            if ambiguity_runs>=t.minimum_repeated_failures and values.ambiguity_rate>=t.unhealthy_ambiguity_rate:
                status=HealthStatus.UNHEALTHY
                reason("REPEATED_AMBIGUITY","ambiguity_rate",values.ambiguity_rate,t.unhealthy_ambiguity_rate)
            if (hard+ambiguity_runs>=t.minimum_repeated_failures
                and values.success_rate<t.minimum_reliable_completion_rate):
                status=HealthStatus.UNHEALTHY
                reason("RELIABLE_COMPLETION_RATE_LOW","success_rate",values.success_rate,t.minimum_reliable_completion_rate)

        recent_ids,previous_ids=[],[]
        if trends and total>=max(t.minimum_runs,t.recent_window+t.historical_window):
            recent=runs[-t.recent_window:]
            previous=runs[-t.recent_window-t.historical_window:-t.recent_window]
            recent_ids,previous_ids=[r.run_id for r in recent],[r.run_id for r in previous]
            # Each comparison uses nonoverlapping complete windows of this tenant.
            def measures(window):
                a=sum(r.primary_locator_attempts for r in window)
                return {
                    "FALLBACK_USAGE_INCREASING":rate(sum(r.fallback_locator_successes for r in window),a),
                    "RECOVERY_USAGE_INCREASING":rate(sum(r.recovery_attempts>0 for r in window),len(window)),
                    "HUMAN_INTERVENTION_INCREASING":rate(sum(r.human_handoff_count>0 or r.human_action_count>0 or r.status==Status.HUMAN_REQUIRED for r in window),len(window)),
                    "SUCCESS_RATE_DECLINING":rate(sum(r.status in {Status.SUCCESS,Status.BUSINESS_OUTCOME} for r in window),len(window)),
                }
            old,new=measures(previous),measures(recent)
            for code in old:
                old_rate,new_rate=old[code],new[code]
                if old_rate is None or new_rate is None:
                    continue
                delta=old_rate-new_rate if code=="SUCCESS_RATE_DECLINING" else new_rate-old_rate
                if delta>=t.trend_rate_delta:
                    reasons.append(HealthReason(code=code,metric="window_rate",previous=old[code],
                                                recent=new[code],threshold=t.trend_rate_delta))
            if all(r.duration_ms is not None for r in [*recent,*previous]):
                old_latency=mean([r.duration_ms for r in previous])
                new_latency=mean([r.duration_ms for r in recent])
                if old_latency and new_latency is not None and new_latency>=old_latency*t.latency_ratio and new_latency-old_latency>=t.latency_minimum_increase_ms:
                    reasons.append(HealthReason(code="LATENCY_REGRESSION",metric="average_latency_ms",
                        previous=old_latency,recent=new_latency,threshold=t.latency_ratio))
            if reasons and status==HealthStatus.HEALTHY:
                status=HealthStatus.DEGRADED
        recommendations={
            HealthStatus.HEALTHY:"Continue monitoring; current samples meet the demo thresholds.",
            HealthStatus.INSUFFICIENT_DATA:"COLLECT_MORE_EVIDENCE",
            HealthStatus.DEGRADED:"REVIEW_RECOMMENDED: review binding and source runs before the next release; unique safe replay may continue.",
            HealthStatus.UNHEALTHY:"NEEDS_REVALIDATION: investigate failure and ambiguity evidence before relying on this binding.",
        }
        return values.model_copy(update={"status":status,"reasons":reasons,"recommendation":recommendations[status],
                                         "historical_run_ids":previous_ids,"recent_run_ids":recent_ids})

    def aggregate(self, capability_id: str, version: str, runs: list[RunMetrics], *,
                  issues: list[EvidenceIssue] | None=None, generated_at: datetime | None=None) -> CapabilityHealth:
        if any((r.capability_id,r.capability_version)!=(capability_id,version) for r in runs):
            raise ValueError("CAPABILITY_METRICS_MISMATCH")
        if len({r.run_id for r in runs})!=len(runs):
            raise ValueError("DUPLICATE_RUN_ID")
        overall=self._assess(runs,trends=False)
        tenants=[TenantHealth(**self._assess([r for r in runs if r.tenant_id==tenant]).model_dump(),tenant_id=tenant)
                 for tenant in sorted({r.tenant_id for r in runs})]
        reasons=list(overall.reasons)
        status=overall.status
        # Global mixing can mask fragile tenants; never average away a bad tenant.
        for tenant in tenants:
            if tenant.status!=HealthStatus.HEALTHY:
                reasons.append(HealthReason(code=f"TENANT_{tenant.status.value}",metric="tenant_health",tenant_id=tenant.tenant_id))
            if tenant.status==HealthStatus.UNHEALTHY:
                status=HealthStatus.UNHEALTHY
            elif tenant.status==HealthStatus.DEGRADED and status!=HealthStatus.UNHEALTHY:
                status=HealthStatus.DEGRADED
            elif tenant.status==HealthStatus.INSUFFICIENT_DATA and status==HealthStatus.HEALTHY:
                status=HealthStatus.INSUFFICIENT_DATA
        if issues:
            reasons.append(HealthReason(code="EVIDENCE_EXCLUDED",metric="invalid_run_bundles",observed=Decimal(len(issues))))
            if status==HealthStatus.HEALTHY:
                status=HealthStatus.INSUFFICIENT_DATA
        recommendation=("Review the named tenant bindings and their evidence; artifacts are unchanged."
                        if status!=HealthStatus.HEALTHY else overall.recommendation)
        return CapabilityHealth(**(overall.model_dump()|{"status":status,"reasons":reasons,"recommendation":recommendation}),
            capability_id=capability_id,capability_version=version,
            generated_at=generated_at or datetime.now(timezone.utc),tenant_health=tenants,
            thresholds=self.thresholds,evidence_issues=issues or [])
