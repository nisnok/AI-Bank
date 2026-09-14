import asyncio
import json

import pytest

from capability_compiler.compiler import CapabilityCompiler, CompilationError
from capability_compiler.spec import member_balance_spec
from deterministic_ui.control import ControlOwner, SessionController
from deterministic_ui.handoff import HandoffManager, HandoffState
from deterministic_ui.models import Observation
from discovery.mock_client import MockModelClient
from discovery.models import DiscoveryLimits, DiscoveryStatus
from discovery.orchestrator import DiscoveryOrchestrator
from operator_ui.scenario import discovery_plans
from test_compiler import CompilerFakeSurface
from test_discovery import request, scripted


class NoticeSurface(CompilerFakeSurface):
    def __init__(self):
        super().__init__()
        self.notice=True
        self.set_match('accessibility','Acknowledge supervisor notice','ack')
        self.set_match('accessibility','Unexpected terminal notice','dialog')
        self.observations['dialog']=Observation(visible=True)

    async def observe(self,target=None):
        obs=await super().observe(target)
        if target is None and 'details' in self.observations and self.notice:
            return obs.model_copy(update={'dialogs':['Supervisor notice']})
        return obs

    async def click(self,target,timeout_ms):
        if target.token=='ack':
            self.notice=False
            self.set_match('accessibility','Unexpected terminal notice')
            self.actions.append(('click','ack'))
        else:
            await super().click(target,timeout_ms)


async def wait_state(manager,state):
    async with asyncio.timeout(2):
        while manager.state!=state:
            await asyncio.sleep(.005)


async def test_interactive_discovery_resumes_existing_manager(tmp_path):
    surface=NoticeSurface()
    controller=SessionController(surface)
    manager=HandoffManager(controller,discovery_plans())
    task=asyncio.create_task(DiscoveryOrchestrator(controller.automation,MockModelClient(scripted),
        handoff=manager,evidence_root=tmp_path).execute(request()))
    await wait_state(manager,HandoffState.PAUSED)
    assert not task.done()
    await manager.take_control()
    assert controller.owner==ControlOwner.HUMAN
    await manager.human_action('acknowledge_notice')
    await manager.handback()
    result=await asyncio.wait_for(task,2)
    assert result.status==DiscoveryStatus.SUCCESS and result.human_action_count==1
    assert surface.actions.count(('click','ack'))==1
    with pytest.raises(CompilationError,match='HUMAN_ASSISTED'):
        CapabilityCompiler().compile(result,member_balance_spec())
    events=[json.loads(line) for line in (tmp_path/result.run_id/'events.jsonl').read_text().splitlines()]
    assert next(e for e in events if e['kind']=='final_result')['model_calls']==result.model_calls


async def test_noninteractive_still_returns_human_required(tmp_path):
    result=await DiscoveryOrchestrator(NoticeSurface(),MockModelClient(scripted),evidence_root=tmp_path).execute(request())
    assert result.status==DiscoveryStatus.HUMAN_REQUIRED and result.code=='DIALOG_PRESENT'
    assert not result.handoff_occurred


async def test_cancel_discovery_handoff(tmp_path):
    controller=SessionController(NoticeSurface())
    manager=HandoffManager(controller,discovery_plans())
    task=asyncio.create_task(DiscoveryOrchestrator(controller.automation,MockModelClient(scripted),
        handoff=manager,evidence_root=tmp_path).execute(request()))
    await wait_state(manager,HandoffState.PAUSED)
    await manager.cancel()
    result=await asyncio.wait_for(task,2)
    assert result.status==DiscoveryStatus.HUMAN_REQUIRED and result.human_action_count==0


def test_interactive_requires_existing_automation_lease():
    raw=NoticeSurface()
    manager=HandoffManager(SessionController(raw),discovery_plans())
    with pytest.raises(ValueError,match='AUTOMATION_LEASE'):
        DiscoveryOrchestrator(raw,MockModelClient(scripted),handoff=manager)


async def test_handoff_deadline_is_bounded(tmp_path):
    controller=SessionController(NoticeSurface())
    manager=HandoffManager(controller,discovery_plans())
    result=await DiscoveryOrchestrator(controller.automation,MockModelClient(scripted),handoff=manager,
        limits=DiscoveryLimits(max_seconds=.15),evidence_root=tmp_path).execute(request())
    assert result.code=='ELAPSED_TIME_LIMIT' and manager.state==HandoffState.FAILED


async def test_human_action_does_not_bypass_identity_checkpoint(tmp_path):
    surface=NoticeSurface()
    controller=SessionController(surface)
    manager=HandoffManager(controller,discovery_plans())
    task=asyncio.create_task(DiscoveryOrchestrator(controller.automation,MockModelClient(scripted),
        handoff=manager,evidence_root=tmp_path).execute(request()))
    await wait_state(manager,HandoffState.PAUSED)
    await manager.take_control()
    await manager.human_action('acknowledge_notice')
    surface.stale=True
    await manager.handback()
    # Checkpoint polling is bounded to two seconds; allow enough time to reject.
    async with asyncio.timeout(4):
        while manager.state!=HandoffState.HUMAN_REQUIRED:
            await asyncio.sleep(.01)
    assert not task.done()
    await manager.cancel()
    result=await asyncio.wait_for(task,2)
    assert result.status==DiscoveryStatus.HUMAN_REQUIRED
    assert not result.outputs


def test_discovery_delegates_control_to_shared_manager():
    import ast
    from pathlib import Path
    tree=ast.parse(Path('src/discovery/orchestrator.py').read_text())
    assert not any(isinstance(node,ast.ClassDef) and 'Handoff' in node.name for node in ast.walk(tree))
    assert not any(isinstance(node,ast.Assign) and any(isinstance(target,ast.Attribute) and target.attr=='owner'
                   for target in node.targets) for node in ast.walk(tree))
    assert any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
               and node.func.attr=='resolve_discovery' for node in ast.walk(tree))
