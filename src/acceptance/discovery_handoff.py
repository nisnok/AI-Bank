"""Real-browser discovery takeover proof; scripted proposals are explicitly labeled."""
import asyncio
from decimal import Decimal
import json
from pathlib import Path

from bank_simulator.server import running_server
from deterministic_ui.control import ControlOwner, SessionController
from deterministic_ui.handoff import HandoffManager, HandoffState
from deterministic_ui.models import TargetRef
from deterministic_ui.playwright_surface import PlaywrightSurface
from deterministic_ui.surface import SurfaceError
from discovery.gemini_client import GeminiModelClient
from discovery.mock_client import MockModelClient
from discovery.models import DiscoveryAction as A, DiscoveryRequest, DiscoveryStatus, ModelDecision
from discovery.orchestrator import DiscoveryOrchestrator
from operator_ui.scenario import discovery_plans
from operator_ui.server import OperatorServer
from .privacy import scan


def proposals(observation, history):
    """Test driver only, never reported as real Gemini discovery."""
    names={element.name:element.id for element in observation.elements}
    if 'Member ID' in names:
        if not history:
            return ModelDecision(action=A.FILL,target_id=names['Member ID'],input_binding='member_id',reason='Fill lookup')
        return ModelDecision(action=A.CLICK,target_id=names['Search'],expected_text='Member Details',reason='Search')
    if not any(item.output_captured for item in history):
        return ModelDecision(action=A.EXTRACT,target_id=names['Savings balance'],output='savings_balance',reason='Read verified balance')
    return ModelDecision(action=A.COMPLETE,reason='Verified result captured')


async def wait_for(manager, states, *, seconds=20):
    async with asyncio.timeout(seconds):
        while manager.state not in states:
            await asyncio.sleep(.01)


async def exercise(root: Path, *, live=False):
    model=GeminiModelClient(env_file=Path('.env')) if live else MockModelClient(proposals)
    with running_server() as server:
        async with PlaywrightSurface.open(server.url+'/?fault=UNEXPECTED_MODAL') as surface:
            controller=SessionController(surface)
            manager=HandoffManager(controller,discovery_plans(),input_source='scripted_acceptance')
            original=next(iter(server.sessions.values()))
            async with OperatorServer(manager):
                task=asyncio.create_task(DiscoveryOrchestrator(controller.automation,model,handoff=manager,
                    evidence_root=root/'runs').execute(DiscoveryRequest(
                        goal='Find member 48321 and retrieve their savings balance.',member_id='48321')))
                try:
                    await wait_for(manager,{HandoffState.PAUSED},seconds=120 if live else 20)
                    assert not task.done()
                    assert (await manager.status())['reason']=='DIALOG_PRESENT'
                    await manager.take_control()
                    count=controller.action_counts[ControlOwner.AUTOMATION]
                    assert controller.owner==ControlOwner.HUMAN
                    # Read actual model-call events before/after HUMAN ownership.
                    assert manager.pending is not None
                    events_path=root/'runs'/manager.pending.run_id/'events.jsonl'
                    calls_before=sum(json.loads(line)['kind']=='model_call' for line in events_path.read_text().splitlines())
                    try:
                        await controller.automation.click(TargetRef(token='forbidden'),100)
                    except SurfaceError:
                        pass
                    else:
                        raise AssertionError('OWNERSHIP_NOT_ENFORCED')
                    await asyncio.sleep(.05)
                    assert controller.action_counts[ControlOwner.AUTOMATION]==count
                    calls_after=sum(json.loads(line)['kind']=='model_call' for line in events_path.read_text().splitlines())
                    assert calls_after==calls_before
                    # A handback without satisfying the plan must not resume discovery.
                    await manager.handback()
                    await wait_for(manager,{HandoffState.HUMAN_REQUIRED})
                    assert not task.done()
                    await manager.take_control()
                    assert await manager.human_action('acknowledge_notice')=='VERIFIED'
                    await manager.handback()
                    result=await asyncio.wait_for(task,90)
                    assert result.status==DiscoveryStatus.SUCCESS
                    assert result.outputs=={'savings_balance':Decimal('1420.75')}
                    assert result.handoff_occurred and result.human_action_count==1
                    assert len(server.sessions)==1 and next(iter(server.sessions.values())) is original
                    assert original.counters.search==1 and original.counters.confirm==original.counters.opened==0
                    records=[json.loads(line) for line in events_path.read_text().splitlines()]
                    assert sum(e['kind']=='human_action_started' for e in records)==1
                    assert any(e['kind']=='resume_rejected' for e in records)
                    resumed=next(i for i,e in enumerate(records) if e['kind']=='discovery_resumed')
                    assert any(e['kind']=='resume_checkpoint_verified' for e in records[:resumed])
                    assert any(e['kind']=='resume_observation' for e in records[:resumed])
                    assert any(e['kind']=='model_call' for e in records[resumed+1:])
                    directory=Path(result.evidence_directory)
                    assert scan(list(directory.rglob('*.json*')))['status']=='PASS'
                    report={'status':'PASS','provider':result.provider,'model':result.model,
                        'model_calls':result.model_calls,'scripted_operator':True,'run_id':result.run_id,
                        'evidence':str(directory),'same_session':True,'automation_actions_during_human_control':0,
                        'model_calls_during_human_control':0,'rejected_unsafe_handback':True,
                        'human_action_count':1,'search_submissions':1,'fresh_observation_and_checkpoint':True,
                        'result':result.status,'balance_verified':True}
                    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
                    return report
                finally:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
