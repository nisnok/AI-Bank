"""Live operator takeover of one retained simulator session; no model calls."""
import argparse
import asyncio
from pathlib import Path

from bank_simulator.server import running_server
from deterministic_ui.control import SessionController
from deterministic_ui.handoff import HandoffManager, HandoffState
from deterministic_ui.models import CapabilityArtifact, Decision, Risk, Status
from deterministic_ui.playwright_surface import PlaywrightSurface
from deterministic_ui.policy import PolicyConfig, PolicyEngine
from deterministic_ui.replay import ReplayEngine
from operator_ui.scenario import savings_plans
from operator_ui.server import OperatorServer


async def scripted_operator(manager):
    """Acceptance driver only: never represent this as a physical person's actions."""
    for action in ("acknowledge_notice", "confirm_account"):
        async with asyncio.timeout(30):
            while manager.state not in {HandoffState.PAUSED, HandoffState.HUMAN_REQUIRED}:
                await asyncio.sleep(.02)
        print(f"HUMAN_REQUIRED: {manager.pending.resume.reason_code if manager.pending and manager.pending.resume else 'unknown'}", flush=True)
        before = manager.controller.action_counts.copy()
        await manager.take_control()
        await asyncio.sleep(.1)
        assert before == manager.controller.action_counts
        print("Same session retained; automation actions during HUMAN control: 0", flush=True)
        outcome = await manager.human_action(action)
        print(f"Scripted operator action: {action}; {outcome}", flush=True)
        await manager.handback()
        while manager.state == HandoffState.RESUMING:
            await asyncio.sleep(.02)


async def run(args):
    artifact_path = Path("capabilities/simulator/prepare_new_savings_subaccount.json")
    original = artifact_path.read_bytes()
    artifact = CapabilityArtifact.model_validate_json(original)
    with running_server() as server:
        # Headless prevents unaudited native input from bypassing the ownership controller.
        # The operator panel displays live state and acts on this very same Page.
        async with PlaywrightSurface.open(server.url + "/?fault=UNEXPECTED_MODAL") as surface:
            controller = SessionController(surface)
            manager = HandoffManager(controller, savings_plans(),
                                     input_source="scripted_acceptance" if args.scripted else "operator_panel")
            policy = PolicyEngine(PolicyConfig(decisions={
                Risk.READ:Decision.ALLOW, Risk.REVERSIBLE_WRITE:Decision.ALLOW,
                Risk.SENSITIVE:Decision.REQUIRE_HUMAN, Risk.IRREVERSIBLE:Decision.REQUIRE_HUMAN}))
            async with OperatorServer(manager) as panel:
                print(f"Operator panel: {panel.url}", flush=True)
                print(f"Retained application session: {controller.session_id}", flush=True)
                replay = ReplayEngine(controller.automation, policy=policy, handoff=manager,
                                      evidence_root=args.evidence_root)
                task = asyncio.create_task(replay.execute(artifact, {"member_id":"48321", "initial_deposit":"500.00"}))
                if args.scripted:
                    await scripted_operator(manager)
                result = await task
                print(f"Result: {result.status}; human_action_count={result.human_action_count}; model_calls={result.model_calls}", flush=True)
                print(f"Evidence: {args.evidence_root}/{result.run_id}", flush=True)
                with server.lock:
                    sessions = list(server.sessions.values())
                    assert len(sessions) == 1
                    session = sessions[0]
                    if result.status == Status.SUCCESS:
                        assert session.counters.search == session.counters.confirm == session.counters.opened == 1
                        assert len(session.subaccounts) == 1
                        print("Session proof: one simulator session; search=1; confirm=1; accounts_opened=1", flush=True)
                assert original == artifact_path.read_bytes()
                if not args.scripted and result.status == Status.SUCCESS:
                    print("Success verified. Keeping the session open for inspection for 30 seconds.", flush=True)
                    await asyncio.sleep(30)
                return 0 if result.status == Status.SUCCESS else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=Path("evidence/handoff"))
    parser.add_argument("--scripted", action="store_true", help="Explicitly labeled automated operator acceptance driver")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
