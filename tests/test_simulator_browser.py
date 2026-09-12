"""Real HTTP + Chromium + existing ReplayEngine. No raw browser scripting."""
import json
import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

import pytest

from bank_simulator.domain import Fault, Stage
from bank_simulator.server import running_server
from deterministic_ui.models import CapabilityArtifact, Decision, Risk, Status
from deterministic_ui.playwright_surface import PlaywrightSurface
from deterministic_ui.policy import PolicyConfig, PolicyEngine
from deterministic_ui.replay import ReplayEngine

pytestmark = pytest.mark.skipif(os.environ.get('RUN_BROWSER_TESTS') != '1', reason='Set RUN_BROWSER_TESTS=1 with Chromium installed')


@pytest.fixture
def simulator():
    with running_server() as server:
        yield server


def load_capability(name='get_member_balance') -> CapabilityArtifact:
    return CapabilityArtifact.model_validate_json(Path(f'capabilities/simulator/{name}.json').read_text())


def policy(decision=Decision.REQUIRE_HUMAN) -> PolicyEngine:
    decisions = dict(PolicyConfig().decisions)
    decisions[Risk.IRREVERSIBLE] = decision
    return PolicyEngine(PolicyConfig(decisions=decisions))


async def execute(simulator, tmp_path, *, member='48321', name='get_member_balance',
                  fault=Fault.NONE, variant='standard', final_decision=Decision.REQUIRE_HUMAN):
    artifact = load_capability(name)
    url = simulator.url + '/?' + urlencode({'fault':fault, 'variant':variant})
    inputs = {'member_id':member}
    if name == 'prepare_new_savings_subaccount':
        inputs['initial_deposit'] = '25.00'
    async with PlaywrightSurface.open(url) as surface:
        result = await ReplayEngine(surface, evidence_root=tmp_path, policy=policy(final_decision)).execute(artifact, inputs)
    events = [json.loads(line) for line in (tmp_path / result.run_id / 'events.jsonl').read_text().splitlines()]
    return result, events


@pytest.mark.parametrize('member,balance', [('48321','1420.75'), ('83921','807.20'), ('77777','65.00')])
async def test_simulator_balance_identity_and_private_evidence(simulator, tmp_path, member, balance):
    result, events = await execute(simulator, tmp_path, member=member)
    assert result.status == Status.SUCCESS
    assert result.outputs == {'savings_balance':Decimal(balance)}
    assert any(e.get('condition_id') == 'correct_member_loaded' and e.get('status') == 'satisfied' for e in events)
    directory = tmp_path / result.run_id
    persisted = ''.join(path.read_text() for path in directory.glob('*.json*'))
    assert f'"{member}"' not in persisted and f'"{balance}"' not in persisted
    assert json.loads((directory / 'result.json').read_text())['outputs'] == {}
    assert (directory / 'screenshots' / 'final.png').is_file()


async def test_simulator_not_found(simulator, tmp_path):
    result, _ = await execute(simulator, tmp_path, member='99999')
    assert result.status == Status.BUSINESS_OUTCOME and result.business_code == 'MEMBER_NOT_FOUND'
    assert not result.outputs and result.failure is None


async def test_simulator_ineligible(simulator, tmp_path):
    result, _ = await execute(simulator, tmp_path, member='77777', name='prepare_new_savings_subaccount')
    assert result.status == Status.BUSINESS_OUTCOME and result.business_code == 'MEMBER_INELIGIBLE'
    session = next(iter(simulator.sessions.values()))
    assert session.counters.confirm == 0 and session.counters.opened == 0


async def test_simulator_slow_page_retries_wait_only(simulator, tmp_path):
    result, events = await execute(simulator, tmp_path, fault=Fault.SLOW_PAGE)
    assert result.status == Status.RECOVERABLE_ERROR
    assert result.failure is not None and result.failure.step_id == 'verify_member'
    attempts = [e for e in events if e['kind'] == 'step_attempt' and e.get('step_id') == 'verify_member']
    assert len(attempts) == 2
    assert len([e for e in events if e['kind'] == 'retry']) == 1
    assert next(iter(simulator.sessions.values())).counters.search == 1
    assert not result.outputs


async def test_simulator_ambiguity_never_submits_search(simulator, tmp_path):
    result, events = await execute(simulator, tmp_path, fault=Fault.AMBIGUOUS_CONTROL)
    assert result.status == Status.HUMAN_REQUIRED
    assert result.failure is not None and result.failure.code == 'AMBIGUOUS_TARGET'
    assert any(e.get('matches') == 2 and e.get('step_id') == 'search_member' for e in events)
    assert next(iter(simulator.sessions.values())).counters.search == 0


async def test_simulator_final_confirmation_requires_human(simulator, tmp_path):
    result, events = await execute(simulator, tmp_path, name='prepare_new_savings_subaccount')
    assert result.status == Status.HUMAN_REQUIRED
    assert result.failure is not None and result.failure.step_id == 'confirm_open_account'
    session = next(iter(simulator.sessions.values()))
    assert session.stage == Stage.REVIEW and session.deposit == Decimal('25.00')
    assert session.counters.confirm == 0 and session.counters.opened == 0
    assert any(e['kind'] == 'policy' and e.get('step_id') == 'confirm_open_account' and e['status'] == 'REQUIRE_HUMAN' for e in events)


async def test_simulator_default_block_still_prevents_confirmation(simulator, tmp_path):
    result, _ = await execute(simulator, tmp_path, name='prepare_new_savings_subaccount', final_decision=Decision.BLOCK)
    assert result.status == Status.HARD_FAILURE
    assert next(iter(simulator.sessions.values())).counters.confirm == 0


async def test_simulator_stale_member_never_extracts(simulator, tmp_path):
    result, events = await execute(simulator, tmp_path, fault=Fault.STALE_MEMBER)
    assert result.status == Status.RECOVERABLE_ERROR and not result.outputs
    assert result.failure is not None and result.failure.expected_condition == 'correct_member_loaded'
    assert not any(e.get('action') == 'extract' for e in events)
    session = next(iter(simulator.sessions.values()))
    assert session.member is not None and session.member.identifier == '83921'


async def test_simulator_label_fallback_succeeds(simulator, tmp_path):
    result, events = await execute(simulator, tmp_path, variant='fallback')
    assert result.status == Status.SUCCESS
    attempts = [e for e in events if e['kind'] == 'locator_attempt' and e.get('step_id') == 'enter_member_id' and 'condition_id' not in e]
    assert [(e['strategy'], e['matches']) for e in attempts] == [('accessibility',0), ('label',1)]
    assert next(iter(simulator.sessions.values())).counters.search == 1


async def test_simulator_confirmation_works_only_with_explicit_test_allow(simulator, tmp_path):
    # This isolated fictional session proves the final UI really mutates state.
    # The reviewer-facing runner has no ALLOW switch for irreversible actions.
    result, _ = await execute(simulator, tmp_path, name='prepare_new_savings_subaccount', final_decision=Decision.ALLOW)
    assert result.status == Status.SUCCESS
    session = next(iter(simulator.sessions.values()))
    assert session.stage == Stage.CONFIRMED
    assert session.counters.confirm == 1 and session.counters.opened == 1
    assert session.subaccounts[0].member_id == '48321'
    assert session.subaccounts[0].balance == Decimal('25.00')


@pytest.mark.parametrize('fault', [Fault.SESSION_EXPIRED, Fault.PERMISSION_DENIED, Fault.UNEXPECTED_MODAL])
async def test_simulator_operational_faults_stop_safely(simulator, tmp_path, fault):
    result, _ = await execute(simulator, tmp_path, name='prepare_new_savings_subaccount', fault=fault)
    assert result.status == Status.RECOVERABLE_ERROR
    session = next(iter(simulator.sessions.values()))
    assert session.counters.confirm == 0 and session.counters.opened == 0
    if fault == Fault.UNEXPECTED_MODAL:
        assert session.counters.begin == 0
