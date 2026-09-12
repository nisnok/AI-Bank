import ast
import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from deterministic_ui.models import Decision, Observation, ObservedElement, Risk, SemanticTarget
from deterministic_ui.policy import PolicyConfig, PolicyEngine
from discovery.gemini_client import GeminiModelClient
from discovery.mock_client import MockModelClient
from discovery.model_client import InvalidModelOutput
from discovery.models import DiscoveryAction as A, DiscoveryLimits, DiscoveryRequest, DiscoveryStatus as S, ModelDecision
from discovery.orchestrator import DiscoveryOrchestrator
from fake_surface import FakeSurface


def target(role, name):
    return SemanticTarget.model_validate({'concept':'observed_control', 'strategies':[{'type':'accessibility','role':role,'name':name}]})


def element(id, name, role='textbox', text='', value=None):
    return ObservedElement(id=id, name=name, role=role, kind='input' if role=='textbox' else 'button',
                           text=text, value=value, target=target(role,name))


class DiscoveryFakeSurface(FakeSurface):
    def __init__(self):
        super().__init__()
        self.stale = False
        self.risky = False

    async def click(self, target, timeout_ms):
        if self.member_id == '99999':
            self.set_match('accessibility', 'Member not found', 'missing')
            self.observations['missing'] = Observation(visible=True, text='Member not found')
            self.actions.append(('click', target.token))
            return
        await super().click(target, timeout_ms)
        self.set_match('accessibility', 'Loaded member identifier', 'identity')

    async def observe(self, target=None):
        if target is not None:
            return await super().observe(target)
        if 'missing' in self.observations:
            return Observation(visible=True, text='Member not found', elements=[element('missing','Member not found','alert','Member not found')])
        if self.risky:
            self.set_match('accessibility','Confirm / Open Account','confirm')
            return Observation(visible=True,text='Account review',elements=[element('confirm','Confirm / Open Account','button')])
        if 'details' in self.observations:
            return Observation(visible=True, text='Member Details', elements=[
                element('identity','Loaded member identifier','status','83921' if self.stale else self.member_id),
                element('balance','Savings balance','status','1234.56'),
            ])
        return Observation(visible=True,text='Member Search',elements=[
            element('member','Member ID',value=self.member_id), element('search','Search','button')])


def scripted(observation, history):
    names = {element.name:element.id for element in observation.elements}
    if not history:
        return ModelDecision(action=A.FILL,target_id=names['Member ID'],input_binding='member_id',reason='Fill the search field.')
    if history[-1].action == A.FILL:
        return ModelDecision(action=A.CLICK,target_id=names['Search'],expected_text='Member Details',reason='Submit the member search.')
    if 'Savings balance' in names and not any(h.output_captured for h in history):
        return ModelDecision(action=A.EXTRACT,target_id=names['Savings balance'],output='savings_balance',reason='Read the displayed savings balance.')
    return ModelDecision(action=A.COMPLETE,reason='The balance was verified and captured.')


def request(member='48321'):
    return DiscoveryRequest(goal=f'Find member {member} and retrieve their savings balance.',member_id=member)


async def execute(tmp_path, client=None, surface=None, limits=None, policy=None, member='48321'):
    return await DiscoveryOrchestrator(surface or DiscoveryFakeSurface(), client or MockModelClient(scripted),
                                       evidence_root=tmp_path, limits=limits, policy=policy).execute(request(member))


def test_structured_decision_validation():
    decision = ModelDecision(action=A.FILL,target_id='e0',input_binding='member_id',reason='Fill search input.')
    assert ModelDecision.model_validate_json(decision.model_dump_json()) == decision


@pytest.mark.parametrize('data', [
    {'action':'EVAL','reason':'Run script'},
    {'action':'CLICK','reason':'No target'},
    {'action':'FILL','target_id':'e0','value':'secret','reason':'Literal value'},
    {'action':'COMPLETE','output':'invented','reason':'Invent balance'},
    {'action':'CLICK','target_id':'e0','reason':'No postcondition'},
])
def test_invalid_and_unsupported_decisions(data):
    with pytest.raises(ValidationError):
        ModelDecision.model_validate(data)


def test_gemini_parser_ignores_thought_and_tracks_usage():
    decision = ModelDecision(action=A.COMPLETE,reason='Finished.')
    result = GeminiModelClient.parse_response({'candidates':[{'finishReason':'STOP','content':{'parts':[
        {'thought':True,'text':'Never persist this reasoning.'},{'text':decision.model_dump_json()}]}}],
        'usageMetadata':{'promptTokenCount':5,'candidatesTokenCount':7,'thoughtsTokenCount':3}})
    assert result.decision == decision and result.usage.input_tokens == 5 and result.usage.thinking_tokens == 3
    with pytest.raises(InvalidModelOutput):
        GeminiModelClient.parse_response({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'not json'}]}}]})


async def test_mock_discovery_success_and_private_trajectory(tmp_path):
    result = await execute(tmp_path)
    assert result.status == S.SUCCESS and result.outputs == {'savings_balance':Decimal('1234.56')}
    assert result.model_calls == 4
    assert [s.compilation_eligible for s in result.trajectory] == [True,True,True,False]
    assert all(s.executed and s.verified for s in result.trajectory[:3])
    persisted = ''.join(file.read_text() for file in Path(result.evidence_directory).glob('*.json*'))
    assert '48321' not in persisted and '1234.56' not in persisted
    meta = json.loads((Path(result.evidence_directory)/'metadata.json').read_text())
    assert meta['execution_mode'] == 'llm_discovery' and meta['provider'] == 'mock'
    assert meta['capability_id'] is None


async def test_model_cannot_claim_unextracted_balance(tmp_path):
    result = await execute(tmp_path, MockModelClient([ModelDecision(action=A.COMPLETE,reason='Done')]))
    assert result.status == S.HARD_FAILURE and result.code == 'UNVERIFIED_COMPLETION'
    assert not result.outputs


async def test_business_outcome(tmp_path):
    result = await execute(tmp_path, member='99999')
    assert result.status == S.BUSINESS_OUTCOME and result.code == 'MEMBER_NOT_FOUND'
    assert result.model_calls == 2


async def test_stale_member_cannot_be_extracted(tmp_path):
    surface = DiscoveryFakeSurface()
    surface.stale = True
    result = await execute(tmp_path, surface=surface)
    assert result.status == S.HUMAN_REQUIRED and not result.outputs
    assert not any(action[0] == 'extract' for action in surface.actions)


async def test_risky_confirmation_cannot_bypass_policy(tmp_path):
    surface = DiscoveryFakeSurface()
    surface.risky = True
    client = MockModelClient([ModelDecision(action=A.CLICK,target_id='confirm',expected_text='Opened',reason='Confirm')])
    result = await execute(tmp_path, client, surface, policy=PolicyEngine(PolicyConfig(decisions={Risk.IRREVERSIBLE:Decision.ALLOW})))
    assert result.status == S.HUMAN_REQUIRED and result.code == 'UNREVIEWED_RISK'
    assert not surface.actions and not result.trajectory[0].compilation_eligible


async def test_policy_block(tmp_path):
    surface = DiscoveryFakeSurface()
    result = await execute(tmp_path, surface=surface, policy=PolicyEngine(PolicyConfig(decisions={})))
    assert result.status == S.HARD_FAILURE and not surface.actions


async def test_ambiguous_target_fails_closed(tmp_path):
    surface = DiscoveryFakeSurface()
    surface.set_match('accessibility','Member ID','one','two')
    result = await execute(tmp_path, surface=surface)
    assert result.status == S.HUMAN_REQUIRED and result.code == 'AMBIGUOUS_TARGET'
    assert not surface.actions


async def test_repeated_state_stops(tmp_path):
    client = MockModelClient(lambda obs, history: ModelDecision(action=A.FILL,target_id='member',input_binding='member_id',reason='Fill again'))
    result = await execute(tmp_path, client, limits=DiscoveryLimits(repeat_limit=2))
    assert result.status == S.STUCK and result.model_calls == 3
    assert not result.trajectory[-1].compilation_eligible


async def test_max_step_limit(tmp_path):
    result = await execute(tmp_path, limits=DiscoveryLimits(max_decisions=1))
    assert result.status == S.MAX_STEPS_EXCEEDED and result.model_calls == 1


async def test_model_requests_human(tmp_path):
    result = await execute(tmp_path, MockModelClient([ModelDecision(action=A.REQUEST_HUMAN,reason='Need review')]))
    assert result.status == S.HUMAN_REQUIRED


async def test_failed_postcondition_is_executed_but_not_compilable(tmp_path):
    decisions = [ModelDecision(action=A.FILL,target_id='member',input_binding='member_id',reason='Fill'),
                 ModelDecision(action=A.CLICK,target_id='search',expected_text='Never present',reason='Search')]
    result = await execute(tmp_path, MockModelClient(decisions), limits=DiscoveryLimits(max_decisions=2, action_timeout_ms=30))
    step = result.trajectory[-1]
    assert step.attempted and step.executed and not step.verified and not step.compilation_eligible


async def test_elapsed_limit_includes_model_call(tmp_path):
    class SlowClient(MockModelClient):
        async def decide(self, goal, observation, history, available_actions):
            await asyncio.sleep(1)
            return await super().decide(goal, observation, history, available_actions)
    result = await execute(tmp_path, SlowClient(scripted), limits=DiscoveryLimits(max_seconds=0.02))
    assert result.code == 'ELAPSED_TIME_LIMIT' and result.model_calls == 1


def test_discovery_never_imports_replay_or_capability_runner():
    for file in Path('src/discovery').glob('*.py'):
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {'deterministic_ui.replay', 'examples.run_simulator'}
    for file in Path('src/deterministic_ui').glob('*.py'):
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith('discovery')


def test_provider_is_isolated():
    for file in Path('src/discovery').glob('*.py'):
        if file.name != 'gemini_client.py':
            assert 'generativelanguage.googleapis.com' not in file.read_text()
            assert 'GEMINI_API_KEY' not in file.read_text()


async def test_repeated_action_failures_stop(tmp_path):
    client = MockModelClient(lambda obs, hist: ModelDecision(action=A.WAIT,expected_text='Never visible',reason='Wait for readiness'))
    result = await execute(tmp_path, client, limits=DiscoveryLimits(action_timeout_ms=10, failure_limit=2, repeat_limit=10))
    assert result.status == S.STUCK and result.code == 'REPEATED_FAILURES'
    assert result.model_calls == 2
    assert not any(step.compilation_eligible for step in result.trajectory)


async def test_wait_is_policy_gated(tmp_path):
    client = MockModelClient([ModelDecision(action=A.WAIT,expected_text='Member Search',reason='Wait')])
    result = await execute(tmp_path, client, policy=PolicyEngine(PolicyConfig(decisions={})))
    assert result.status == S.HARD_FAILURE and not result.trajectory[0].executed


async def test_unknown_target_rejected(tmp_path):
    client = MockModelClient([ModelDecision(action=A.CLICK,target_id='invented',expected_text='Done',reason='Click')])
    result = await execute(tmp_path, client)
    assert result.code == 'UNKNOWN_OBSERVATION_TARGET'


async def test_schema_bypass_revalidated(tmp_path):
    from discovery.models import ModelReply
    class MalformedClient(MockModelClient):
        async def decide(self, goal, observation, history, available_actions):
            return ModelReply.model_construct(decision=ModelDecision.model_construct(action='EVAL', reason='Unsupported'))
    result = await execute(tmp_path, MalformedClient([]))
    assert result.status == S.HARD_FAILURE and result.code == 'INVALID_MODEL_OUTPUT'


async def test_unsupported_select_rejected(tmp_path):
    client = MockModelClient([ModelDecision(action=A.SELECT,target_id='member',input_binding='member_id',reason='Select')])
    result = await execute(tmp_path, client)
    assert result.code == 'UNSUPPORTED_ACTION' and not result.trajectory[0].executed


@pytest.mark.parametrize('errors,expected,calls', [(1,S.SUCCESS,5),(3,S.HARD_FAILURE,3)])
async def test_transient_provider_errors_are_bounded_and_counted(tmp_path, monkeypatch, errors, expected, calls):
    from discovery.model_client import ModelError
    class TransientClient(MockModelClient):
        async def decide(self, goal, observation, history, available_actions):
            nonlocal errors
            if errors:
                errors -= 1
                raise ModelError('PROVIDER_HTTP_503')
            return await super().decide(goal, observation, history, available_actions)
    async def no_delay(seconds):
        pass
    monkeypatch.setattr('discovery.orchestrator.asyncio.sleep', no_delay)
    result = await execute(tmp_path, TransientClient(scripted))
    assert result.status == expected and result.model_calls == calls
    if expected == S.HARD_FAILURE:
        assert result.code == 'MODEL_FAILURE_LIMIT' and not result.trajectory


def test_evidence_redacts_unknown_semantic_labels():
    from discovery.evidence import project_strategy
    projected = project_strategy({'type':'relative','role':'button','name':'private customer name',
                                  'anchor':{'type':'text','value':'private account detail'}})
    assert projected['name'] == '[redacted]' and projected['anchor']['value'] == '[redacted]'
    assert project_strategy({'type':'label','value':'Member ID'})['value'] == 'Member ID'
