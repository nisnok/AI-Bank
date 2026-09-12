import asyncio
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from bank_simulator.server import running_server
from deterministic_ui.control import ControlOwner, SessionController
from deterministic_ui.handoff import HandoffManager, HandoffState
from deterministic_ui.models import CapabilityArtifact, Decision, Risk, Status, TargetRef
from deterministic_ui.playwright_surface import PlaywrightSurface
from deterministic_ui.policy import PolicyConfig, PolicyEngine
from deterministic_ui.replay import ReplayEngine
from deterministic_ui.surface import SurfaceError
from operator_ui.scenario import savings_plans
from operator_ui.server import OperatorServer

pytestmark = pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1",
                               reason="Set RUN_BROWSER_TESTS=1 with Chromium installed")


async def request(url, payload=None, *, origin=None):
    def send():
        headers = {"Content-Type":"application/json"}
        if origin:
            headers["Origin"] = origin
        req = Request(url, data=json.dumps(payload).encode() if payload else None, headers=headers)
        try:
            with urlopen(req, timeout=10) as response:
                return response.status, response.read().decode()
        except HTTPError as exc:
            return exc.code, exc.read().decode()
    return await asyncio.to_thread(send)


async def wait_state(manager, states):
    async with asyncio.timeout(10):
        while manager.state not in states:
            await asyncio.sleep(.01)


async def test_same_browser_operator_panel_two_handoffs(tmp_path):
    path = Path("capabilities/simulator/prepare_new_savings_subaccount.json")
    original = path.read_bytes()
    artifact = CapabilityArtifact.model_validate_json(original)
    with running_server() as server:
        async with PlaywrightSurface.open(server.url + "/?fault=UNEXPECTED_MODAL") as surface:
            control = SessionController(surface)
            manager = HandoffManager(control, savings_plans(), input_source="browser_test")
            policy = PolicyEngine(PolicyConfig(decisions={
                Risk.READ:Decision.ALLOW, Risk.REVERSIBLE_WRITE:Decision.ALLOW,
                Risk.IRREVERSIBLE:Decision.REQUIRE_HUMAN}))
            with server.lock:
                assert len(server.sessions) == 1
                original_session = next(iter(server.sessions.values()))
            async with OperatorServer(manager) as panel:
                assert (await request(panel.url))[0] == 200
                assert (await request(panel.url, {"command":"take"}, origin="https://untrusted.invalid"))[0] == 400
                assert (await request(panel.url, {"command":"action","id":"confirm_account"}))[0] == 409
                task = asyncio.create_task(ReplayEngine(control.automation, policy=policy, handoff=manager,
                    evidence_root=tmp_path).execute(artifact, {"member_id":"48321","initial_deposit":"500.00"}))
                for action in ("acknowledge_notice","confirm_account"):
                    await wait_state(manager, {HandoffState.PAUSED,HandoffState.HUMAN_REQUIRED})
                    assert not task.done()
                    state = json.loads((await request(panel.url + "/status"))[1])
                    assert state["session_id"] == control.session_id
                    assert state["reason"] in {"UNEXPECTED_BLOCKING_UI","RISK_REQUIRE_HUMAN"}
                    assert (await request(panel.url, {"command":"take"}))[0] == 200
                    count = control.action_counts[ControlOwner.AUTOMATION]
                    with pytest.raises(SurfaceError):
                        await control.automation.click(TargetRef(token="forbidden"),100)
                    await asyncio.sleep(.03)
                    assert control.action_counts[ControlOwner.AUTOMATION] == count
                    assert (await request(panel.url, {"command":"action","id":action}))[0] == 200
                    if action == "confirm_account":
                        assert (await request(panel.url, {"command":"action","id":action}))[0] == 409
                    assert (await request(panel.url, {"command":"handback"}))[0] == 200
                    await wait_state(manager, {HandoffState.AUTOMATION,HandoffState.PAUSED,HandoffState.COMPLETED})
                result = await asyncio.wait_for(task, 10)
                assert result.status == Status.SUCCESS and result.human_action_count == 2
                with server.lock:
                    assert len(server.sessions) == 1
                    assert next(iter(server.sessions.values())) is original_session
                    assert original_session.counters.search == 1
                    assert original_session.counters.confirm == original_session.counters.opened == 1
                    assert str(original_session.subaccounts[0].balance) == "500.00"
                assert result.model_calls == 0 and original == path.read_bytes()
                summary = json.loads((tmp_path/result.run_id/"control-summary.json").read_text())
                assert len(summary["ownership_checks"]) == 2
                assert all(check["automation_actions_during_human_control"] == 0 for check in summary["ownership_checks"])
                records = list((tmp_path/result.run_id).glob("human-action-*.json"))
                assert len(records) == 2
                text = "".join(p.read_text() for p in (tmp_path/result.run_id).glob("*.json*"))
                assert "48321" not in text and "500.00" not in text
