import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest

from deterministic_ui.models import CapabilityArtifact, Decision, Observation, Risk, Status
from deterministic_ui.policy import PolicyConfig, PolicyEngine
from deterministic_ui.replay import ReplayEngine
from deterministic_ui.surface import SurfaceError, SurfaceTimeout


def engine(surface, tmp_path, policy=None):
    return ReplayEngine(surface, evidence_root=tmp_path, policy=policy)


async def test_success_and_private_evidence(artifact, surface, tmp_path):
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"private-member-998"})
    assert result.status == Status.SUCCESS
    assert result.outputs == {"savings_balance":Decimal("1234.56")}
    assert isinstance(result.outputs["savings_balance"], Decimal)
    folder = tmp_path / result.run_id
    assert (folder / "metadata.json").is_file()
    assert (folder / "result.json").is_file()
    assert len(list((folder / "screenshots").glob("*.png"))) == 4
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
    assert events[-1]["status"] == "SUCCESS"
    assert all(e["run_id"] == result.run_id and e["execution_mode"] == "deterministic_replay" for e in events)
    assert any(e["kind"] == "step_finished" and "duration_ms" in e for e in events)
    assert any(e["kind"] == "locator_result" and e["quality"] == "semantic" for e in events)
    persisted = ''.join(path.read_text() for path in folder.glob("*.json*"))
    for secret in ("private-member-998", "Sensitive name", "1234.56"):
        assert secret not in persisted
    assert json.loads((folder / "result.json").read_text())["outputs"] == {}


async def test_invalid_inputs_do_not_act(artifact, surface, tmp_path):
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":123})
    assert result.failure is not None
    assert result.status == Status.HARD_FAILURE and result.failure.code == "INVALID_INPUTS"
    assert not surface.actions and not surface.queries


async def test_business_outcome(artifact, surface, tmp_path):
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"missing-secret"})
    assert result.status == Status.BUSINESS_OUTCOME and result.business_code == "MEMBER_NOT_FOUND"
    assert result.failure is None and not result.outputs
    assert [action[0] for action in surface.actions] == ["fill", "click"]


async def test_ambiguous_replay_does_not_act(artifact, surface, tmp_path):
    surface.set_match("accessibility", "Member ID", "one", "two")
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"secret"})
    assert result.failure is not None
    assert result.status == Status.HUMAN_REQUIRED and result.failure.code == "AMBIGUOUS_TARGET"
    assert result.failure.step_id == "enter_member_id" and result.failure.evidence_refs
    assert not surface.actions


async def test_no_target_hard_failure(artifact, surface, tmp_path):
    surface.matches.clear()
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"secret"})
    assert result.failure is not None
    assert result.status == Status.HARD_FAILURE and result.failure.code == "NO_TARGET"
    assert not result.failure.retryable and not surface.actions


@pytest.mark.parametrize('decision,status', [(Decision.BLOCK,Status.HARD_FAILURE), (Decision.REQUIRE_HUMAN,Status.HUMAN_REQUIRED)])
async def test_policy_prevents_action(artifact, surface, tmp_path, decision, status):
    policy = PolicyEngine(PolicyConfig(decisions={Risk.REVERSIBLE_WRITE:decision}))
    result = await engine(surface, tmp_path, policy).execute(artifact, {"member_id":"secret"})
    assert result.status == status and not surface.actions


async def test_retry_is_bounded_and_explicit(artifact, surface, tmp_path):
    surface.fail_fills = 1
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"secret"})
    assert result.status == Status.SUCCESS
    assert len([a for a in surface.actions if a[0] == "fill"]) == 2
    surface.fail_fills = 10
    surface.actions.clear()
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"secret"})
    assert result.status == Status.RECOVERABLE_ERROR
    assert len(surface.actions) == 2
    assert "SECRET" not in (tmp_path / result.run_id / "events.jsonl").read_text()


async def test_uncertain_click_is_not_repeated(artifact, surface, tmp_path):
    async def uncertain():
        raise SurfaceTimeout("sensitive provider detail")
    surface.on_click = uncertain
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"secret"})
    assert result.status == Status.RECOVERABLE_ERROR
    assert len([a for a in surface.actions if a[0] == "click"]) == 1
    assert result.failure is not None
    assert "may have completed" in result.failure.safe_next_action
    assert not result.failure.retryable


async def test_delayed_business_outcome(artifact, surface, tmp_path):
    tasks: list[asyncio.Task[None]] = []
    async def delayed():
        async def finish():
            await asyncio.sleep(0.03)
            surface.set_match("text", "Member not found", "missing")
            surface.observations["missing"] = Observation(visible=True)
        tasks.append(asyncio.create_task(finish()))
    surface.on_click = delayed
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"secret"})
    await tasks[0]
    assert result.status == Status.BUSINESS_OUTCOME


async def test_failed_postcondition(artifact_data, surface, tmp_path):
    artifact_data["steps"][1]["timeout_ms"] = 20
    artifact = CapabilityArtifact.model_validate(artifact_data)
    async def no_change():
        pass
    surface.on_click = no_change
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"secret"})
    assert result.status == Status.RECOVERABLE_ERROR
    assert result.failure is not None
    assert result.failure.expected_condition == "member_details_visible"
    assert result.failure.step_id == "search_member"


async def test_invalid_extracted_value(artifact, surface, tmp_path):
    original = surface.click
    async def click(target, timeout_ms):
        await original(target, timeout_ms)
        surface.observations["balance"] = Observation(visible=True, text="$not-a-number-secret")
    surface.click = click
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"secret"})
    assert result.failure is not None
    assert result.status == Status.HARD_FAILURE and result.failure.code == "INVALID_OUTPUT"
    assert "$not-a-number-secret" not in (tmp_path / result.run_id / "result.json").read_text()


async def test_provider_failure_redacted(artifact, surface, tmp_path):
    async def broken(strategy):
        raise SurfaceError("private account 1234")
    surface.query = broken
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"secret"})
    assert result.failure is not None
    assert result.status == Status.HARD_FAILURE and result.failure.code == "SURFACE_ERROR"
    assert "private account" not in (tmp_path / result.run_id / "result.json").read_text()


async def test_incompatible_surface(artifact, surface, tmp_path):
    surface.features = frozenset()
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"secret"})
    assert result.failure is not None
    assert result.failure.code == "INCOMPATIBLE_SURFACE" and not surface.actions


async def test_evidence_unavailable_blocks_execution(artifact, surface, tmp_path):
    root = tmp_path / "file"
    root.write_text("not a directory")
    result = await ReplayEngine(surface, evidence_root=root).execute(artifact, {"member_id":"secret"})
    assert result.failure is not None
    assert result.failure.code == "EVIDENCE_UNAVAILABLE" and not surface.actions


async def test_screenshot_failure_does_not_fail_safe_run(artifact, surface, tmp_path):
    async def broken(path):
        raise SurfaceError("private screenshot error")
    surface.screenshot = broken
    result = await engine(surface, tmp_path).execute(artifact, {"member_id":"secret"})
    assert result.status == Status.SUCCESS
    assert "CAPTURE_UNAVAILABLE" in (tmp_path / result.run_id / "events.jsonl").read_text()


async def test_final_success_checkpoint_required(artifact_data, surface, tmp_path):
    artifact_data["success"]["expected"] = {"kind":"text_equals", "value":"never-matches"}
    artifact_data["steps"][-1]["timeout_ms"] = 20
    result = await engine(surface, tmp_path).execute(CapabilityArtifact.model_validate(artifact_data), {"member_id":"secret"})
    assert result.status == Status.RECOVERABLE_ERROR and not result.outputs
    assert result.failure is not None
    assert result.failure.expected_condition == "balance_visible"
