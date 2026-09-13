import ast
from decimal import Decimal
from pathlib import Path

import pytest

from capability_eval.analysis import classify, summarize
from capability_eval.models import EvaluationRun, FailureAnalysis, FailureCode as F, PageFacts, Scenario
from capability_eval.scenarios import SCENARIOS
from deterministic_ui.evidence import Event
from deterministic_ui.models import CapabilityArtifact, Failure, RunResult, Status
from deterministic_ui.replay import ReplayEngine
from test_health import metric


@pytest.fixture
def canonical():
    return CapabilityArtifact.model_validate_json(Path("capabilities/generated/get_member_balance/1.0.0/validated.json").read_text())


def failed(canonical, condition=None, code="CONDITION_TIMEOUT", step_index=0):
    return RunResult(run_id="run",status=Status.RECOVERABLE_ERROR,
        failure=Failure(run_id="run",step_id=canonical.steps[step_index].id,code=code,
                        expected_condition=condition,safe_next_action="Inspect evidence"))


def facts(**updates):
    return PageFacts(**({"expected_input_role_present":True,"loading":False,"unexpected_workspace":False}|updates))


def attempts(canonical):
    return [Event(run_id="run",kind="locator_attempt",step_id=canonical.steps[0].id,
                  condition_id="input_visible",strategy_index=i,strategy=strategy,matches=0,status="no_match")
            for i,strategy in enumerate(["accessibility","label","css"])]


@pytest.mark.parametrize("kind,expected", [
    ("exhausted",F.FALLBACK_EXHAUSTED),("missing",F.REQUIRED_ELEMENT_MISSING),
    ("stale",F.PAGE_STATE_INVALID),("partial",F.PAGE_STATE_INVALID),("unexpected",F.PAGE_STATE_INVALID),
    ("pre",F.PRECONDITION_FAILED),("post",F.POSTCONDITION_FAILED),("ambiguous",F.AMBIGUOUS_TARGET)])
def test_failure_classification_uses_observed_evidence(canonical,kind,expected):
    result=failed(canonical,"input_value_verified" if kind=="post" else "input_visible",
                  "AMBIGUOUS_TARGET" if kind=="ambiguous" else "CONDITION_TIMEOUT")
    current=facts(expected_input_role_present=kind!="missing",loading=kind=="partial",
                  unexpected_workspace=kind=="unexpected",identity_matches=False if kind=="stale" else None)
    events=attempts(canonical) if kind=="exhausted" else []
    assert classify(result,canonical,current,events).code==expected


def test_primary_failure_recovered_is_a_finding_not_failed_run(canonical):
    result=RunResult(run_id="run",status=Status.SUCCESS)
    analysis=classify(result,canonical,facts(),attempts(canonical))
    assert analysis.code is None and F.PRIMARY_LOCATOR_FAILED in analysis.findings


def test_business_outcome_is_not_infrastructure_failure(canonical):
    result=RunResult(run_id="run",status=Status.BUSINESS_OUTCOME,business_code="MEMBER_NOT_FOUND")
    assert classify(result,canonical,facts(),[]).code is None


def test_evaluation_metric_denominators(canonical):
    records=[]
    for i,status in enumerate([Status.SUCCESS,Status.SUCCESS,Status.BUSINESS_OUTCOME,
                               Status.RECOVERABLE_ERROR,Status.HUMAN_REQUIRED]):
        fallback=i==1
        m=metric(i,status=status,primary_locator_successes=2 if fallback else 3,
                 fallback_locator_successes=int(fallback),drift_signal_count=3 if fallback else 0)
        records.append(EvaluationRun(scenario=Scenario(id=f"scenario_{i}"),metrics=m,page_facts=facts(),
            analysis=FailureAnalysis(code=F.REQUIRED_ELEMENT_MISSING if i==3 else F.AMBIGUOUS_TARGET if i==4 else None),
            fallback_attempted=i in {1,3},fallback_recovered=fallback,expectation_met=True))
    summary=summarize(canonical,records)
    assert summary.total_runs==5 and summary.success_rate==Decimal(".6")
    assert summary.primary_locator_success_rate==Decimal(".9333")
    assert summary.fallback_usage_rate==Decimal(".0667")
    assert summary.fallback_recovery_rate==Decimal(".5")
    assert summary.unrecoverable_failure_rate==summary.human_intervention_rate==Decimal(".2")
    assert summary.drift_event_count==3 and summary.expectation_pass_rate==1
    assert summary.failure_counts=={"AMBIGUOUS_TARGET":1,"REQUIRED_ELEMENT_MISSING":1}


def test_empty_evaluation_rates_are_explicit(canonical):
    summary=summarize(canonical,[])
    assert summary.total_runs==0 and summary.primary_locator_success_rate is None
    assert summary.fallback_recovery_rate is None and summary.most_common_failure is None


async def test_timeout_reports_actual_precondition(artifact,surface,tmp_path):
    condition=artifact.steps[1].postcondition
    assert condition is not None
    step=artifact.steps[0].model_copy(update={"precondition":condition,"postcondition":artifact.success,"timeout_ms":10})
    changed=artifact.model_copy(update={"steps":[step,*artifact.steps[1:]]})
    result=await ReplayEngine(surface,evidence_root=tmp_path).execute(changed,{"member_id":"secret"})
    assert result.failure is not None and result.failure.expected_condition==condition.id
    assert not surface.actions


def test_scenarios_do_not_persist_sensitive_oracle_inputs():
    for scenario in SCENARIOS:
        data=scenario.model_dump_json()
        assert "member_id" not in data and "expected_balance" not in data


def test_evaluation_has_no_model_or_browser_dependency():
    for path in Path("src/capability_eval").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            modules=[a.name for a in node.names] if isinstance(node,ast.Import) else (
                [node.module or ""] if isinstance(node,ast.ImportFrom) else [])
            assert not any(module.split(".")[0] in {"discovery","playwright","google","openai","anthropic"} for module in modules)
    assert "capability_eval" not in Path("src/deterministic_ui/replay.py").read_text()
