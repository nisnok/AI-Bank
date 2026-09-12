import asyncio
import json

import pytest

from deterministic_ui.control import ControlOwner, SessionController
from deterministic_ui.handoff import HandoffManager, HandoffState, OperatorAction, ResumePlan
from deterministic_ui.models import (Action, CapabilityArtifact, Condition, Decision, Observation,
    Risk, SemanticTarget, Status, Step, TargetRef, Text, RetryPolicy)
from deterministic_ui.policy import PolicyConfig, PolicyEngine
from deterministic_ui.replay import ReplayEngine
from deterministic_ui.surface import SurfaceError, SurfaceTimeout
from fake_surface import FakeSurface


def condition(name):
    return Condition(id=name, target=SemanticTarget(concept=name, strategies=[Text(value=name)]))


class HandoffFake(FakeSurface):
    def __init__(self):
        super().__init__()
        self.observed = 0
        self.set_match("text", "submit", "submit")
        self.observations["page"] = Observation(visible=True, text="sensitive-member-48321")

    async def observe(self, target=None):
        self.observed += 1
        return await super().observe(target)

    async def click(self, target, timeout_ms):
        self.actions.append(("click", target.token))
        self.set_match("text", "done", "done")
        self.observations["done"] = Observation(visible=True)


def mutation_artifact(artifact):
    done = condition("done")
    step = Step(id="submit", action=Action.CLICK, target=condition("submit").target,
                risk=Risk.IRREVERSIBLE, postcondition=done, timeout_ms=25)
    return artifact.model_copy(update={"steps":[step], "outputs":{}, "success":done,
        "safety":artifact.safety.model_copy(update={"max_risk":Risk.IRREVERSIBLE})})


def setup(artifact, tmp_path, *, raw=None):
    raw = raw or HandoffFake()
    controller = SessionController(raw)
    action = OperatorAction(id="submit", label="Submit", target=condition("submit").target,
                            irreversible=True, postconditions=[condition("done")])
    manager = HandoffManager(controller, {"submit":ResumePlan(completed=[condition("done")], actions=[action])},
                             input_source="unit_test")
    policy = PolicyEngine(PolicyConfig(decisions={Risk.IRREVERSIBLE:Decision.REQUIRE_HUMAN}))
    engine = ReplayEngine(controller.automation, policy=policy, handoff=manager, evidence_root=tmp_path)
    return raw, controller, manager, engine


async def paused(manager):
    async with asyncio.timeout(3):
        while manager.state not in {HandoffState.PAUSED, HandoffState.HUMAN_REQUIRED}:
            await asyncio.sleep(.001)


async def test_takeover_resume_audit_and_no_duplicate_mutation(artifact, tmp_path):
    artifact = mutation_artifact(artifact)
    original = artifact.model_dump_json()
    raw, control, manager, engine = setup(artifact, tmp_path)
    task = asyncio.create_task(engine.execute(artifact, {"member_id":"private-input"}))
    await paused(manager)
    assert manager.pending and manager.pending.status == Status.HUMAN_REQUIRED
    assert not raw.actions
    with pytest.raises(SurfaceError):
        await manager.human_action("submit")
    await manager.take_control()
    for operation in (control.automation.click(TargetRef(token="submit"),100),
                      control.automation.fill(TargetRef(token="member"),"secret",100)):
        with pytest.raises(SurfaceError):
            await operation
    assert not raw.actions
    await manager.human_action("submit")
    with pytest.raises(SurfaceError):
        await manager.human_action("submit")
    observed = raw.observed
    await manager.handback()
    result = await asyncio.wait_for(task, 3)
    assert result.status == Status.SUCCESS and result.handoff_occurred
    assert result.human_action_count == 1 and result.model_calls == 0
    assert raw.observed > observed
    assert raw.actions == [("click","submit")]
    assert control.action_counts[ControlOwner.AUTOMATION] == 0
    assert artifact.model_dump_json() == original
    folder = tmp_path/result.run_id
    events = [json.loads(line) for line in (folder/"events.jsonl").read_text().splitlines()]
    kinds = [e["kind"] for e in events]
    expected = ["handoff_requested","automation_paused","control_transferred","human_action",
                "handback_requested","control_returned","resume_observation",
                "resume_checkpoint_verified","resumed","final_result"]
    positions = [kinds.index(kind) for kind in expected]
    assert positions == sorted(positions)
    record = json.loads((folder/"human-action-1.json").read_text())
    assert record["actor"] == "HUMAN" and record["input_source"] == "unit_test"
    assert record["session_id"] == control.session_id
    assert record["target"] == "submit" and "before" in record and "after" in record
    persisted = "".join(p.read_text() for p in folder.glob("*.json*"))
    assert "private-input" not in persisted and "sensitive-member-48321" not in persisted


async def test_invalid_handback_stays_paused(artifact, tmp_path):
    artifact = mutation_artifact(artifact)
    raw, control, manager, engine = setup(artifact, tmp_path)
    task = asyncio.create_task(engine.execute(artifact, {"member_id":"secret"}))
    await paused(manager)
    await manager.take_control()
    await manager.handback()
    await paused(manager)
    assert not task.done() and not raw.actions
    assert manager.state == HandoffState.HUMAN_REQUIRED
    await manager.cancel()
    result = await task
    assert result.status == Status.HUMAN_REQUIRED


async def test_lease_transfer_waits_for_inflight_action():
    raw = HandoffFake()
    entered, release = asyncio.Event(), asyncio.Event()
    async def click(target, timeout_ms):
        entered.set()
        await release.wait()
    raw.click = click
    control = SessionController(raw)
    running = asyncio.create_task(control.automation.click(TargetRef(token="submit"),1000))
    await entered.wait()
    async def transfer():
        async with control.lock:
            control.owner = ControlOwner.HUMAN
    transferring = asyncio.create_task(transfer())
    await asyncio.sleep(.01)
    assert not transferring.done()
    release.set()
    await running
    await transferring
    assert control.owner == ControlOwner.HUMAN


async def test_ambiguous_target_escalates_without_action(artifact, tmp_path):
    artifact = mutation_artifact(artifact)
    raw, _, manager, engine = setup(artifact, tmp_path)
    raw.set_match("text","submit","first","second")
    task = asyncio.create_task(engine.execute(artifact, {"member_id":"secret"}))
    await paused(manager)
    assert manager.pending and manager.pending.failure and manager.pending.failure.code == "AMBIGUOUS_TARGET"
    assert not raw.actions
    await manager.cancel()
    assert (await task).status == Status.HUMAN_REQUIRED


@pytest.mark.parametrize("completed", [True, False])
async def test_uncertain_irreversible_never_repeated_even_if_marked_repeatable(artifact, tmp_path, completed):
    artifact = mutation_artifact(artifact)
    step = artifact.steps[0].model_copy(update={"retry":RetryPolicy(max_attempts=3, safe_to_repeat=True)})
    artifact = artifact.model_copy(update={"steps":[step]})
    raw = HandoffFake()
    original = raw.click
    async def uncertain(target, timeout_ms):
        if completed:
            await original(target, timeout_ms)
        else:
            raw.actions.append(("click",target.token))
        raise SurfaceTimeout("secret")
    raw.click = uncertain
    policy = PolicyEngine(PolicyConfig(decisions={Risk.IRREVERSIBLE:Decision.ALLOW}))
    result = await ReplayEngine(raw, policy=policy, evidence_root=tmp_path).execute(artifact, {"member_id":"secret"})
    assert len(raw.actions) == 1
    assert result.status == (Status.SUCCESS if completed else Status.HUMAN_REQUIRED)
    if not completed:
        assert result.failure and result.failure.code == "UNCERTAIN_MUTATION"


async def test_business_outcome_does_not_handoff(artifact, surface, tmp_path):
    control = SessionController(surface)
    manager = HandoffManager(control, {})
    result = await ReplayEngine(control.automation, handoff=manager, evidence_root=tmp_path).execute(
        artifact, {"member_id":"missing-secret"})
    assert result.status == Status.BUSINESS_OUTCOME and not manager.handoff_occurred


async def test_bounded_recovery_before_any_handoff(artifact, surface, tmp_path):
    surface.fail_fills = 1
    control = SessionController(surface)
    manager = HandoffManager(control, {})
    result = await ReplayEngine(control.automation, handoff=manager, evidence_root=tmp_path).execute(
        artifact, {"member_id":"secret"})
    assert result.status == Status.SUCCESS and not manager.handoff_occurred
    assert len([a for a in surface.actions if a[0]=="fill"]) == 2


async def test_human_fill_is_redacted(artifact, tmp_path):
    artifact = mutation_artifact(artifact)
    raw, control, manager, engine = setup(artifact, tmp_path)
    fill = OperatorAction(id="enter_value", label="Enter value", action=Action.FILL,
                          target=condition("submit").target)
    manager.plans["submit"] = ResumePlan(actions=[fill])
    task = asyncio.create_task(engine.execute(artifact, {"member_id":"secret"}))
    await paused(manager)
    await manager.take_control()
    await manager.human_action("enter_value", "private-typed-value")
    await manager.cancel()
    result = await task
    record = json.loads((tmp_path/result.run_id/"human-action-1.json").read_text())
    assert record["action"] == "fill" and record["value"] == "[redacted]"
    assert "private-typed-value" not in json.dumps(record)


async def test_resume_continues_remaining_steps_without_restart(artifact, tmp_path):
    artifact = mutation_artifact(artifact)
    following = Step(id="continue_read", action=Action.WAIT, target=condition("done").target,
                     postcondition=condition("done"), risk=Risk.READ)
    artifact = artifact.model_copy(update={"steps":[*artifact.steps, following]})
    raw, control, manager, engine = setup(artifact, tmp_path)
    engine.policy = PolicyEngine(PolicyConfig(decisions={
        Risk.IRREVERSIBLE:Decision.REQUIRE_HUMAN, Risk.READ:Decision.ALLOW}))
    task = asyncio.create_task(engine.execute(artifact, {"member_id":"secret"}))
    await paused(manager)
    await manager.take_control()
    await manager.human_action("submit")
    await manager.handback()
    result = await task
    assert result.status == Status.SUCCESS and len(raw.actions) == 1
    events = [json.loads(line) for line in (tmp_path/result.run_id/"events.jsonl").read_text().splitlines()]
    assert [e["step_id"] for e in events if e["kind"]=="step_started"] == ["submit","continue_read"]


async def test_post_action_ambiguity_does_not_authorize_retry(artifact, tmp_path):
    artifact = mutation_artifact(artifact)
    step = artifact.steps[0].model_copy(update={"risk":Risk.REVERSIBLE_WRITE})
    artifact = artifact.model_copy(update={"steps":[step]})
    raw, control, manager, engine = setup(artifact, tmp_path)
    async def ambiguous_after_click(target, timeout_ms):
        raw.actions.append(("click", target.token))
        raw.set_match("text","done","one","two")
    raw.click = ambiguous_after_click
    raw.set_match("text","ready","ready")
    raw.observations["ready"] = Observation(visible=True)
    manager.plans["submit"] = ResumePlan(retry=[condition("ready")])
    engine.policy = PolicyEngine()
    task = asyncio.create_task(engine.execute(artifact, {"member_id":"secret"}))
    await paused(manager)
    assert manager.pending and manager.pending.failure and manager.pending.failure.action_attempted
    await manager.take_control()
    await manager.handback()
    await paused(manager)
    assert raw.actions == [("click","submit")] and not task.done()
    await manager.cancel()
    await task
