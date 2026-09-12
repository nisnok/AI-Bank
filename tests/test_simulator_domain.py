from decimal import Decimal

import pytest
from pydantic import ValidationError

from bank_simulator.domain import Fault, Session, Stage
from deterministic_ui.models import CapabilityArtifact
from deterministic_ui.templates import bind_conditions


@pytest.mark.parametrize('identifier,state', [('48321','DETAILS'), ('83921','DETAILS'), ('77777','DETAILS'), ('99999','MEMBER_NOT_FOUND')])
def test_seed_members(identifier, state):
    session = Session()
    assert session.search(identifier) == state
    if state == 'DETAILS':
        assert session.member is not None and session.member.identifier == identifier


def test_confirm_is_stateful_and_cannot_double_post():
    session = Session()
    assert session.confirm() == 'INVALID_STATE'
    session.search('48321')
    assert session.begin() == 'OPENING'
    assert session.review('25.50') == 'REVIEW'
    assert session.counters.opened == 0
    assert session.confirm() == 'CONFIRMED'
    assert session.stage == Stage.CONFIRMED and session.deposit == Decimal('25.50')
    assert session.confirm() == 'INVALID_STATE'
    assert session.counters.opened == 1
    session.search('48321')
    assert len(session.subaccounts) == 1
    assert session.subaccounts[0].member_id == '48321'
    assert session.subaccounts[0].balance == Decimal('25.50')


@pytest.mark.parametrize('value', ['-1', '0', 'NaN', 'Infinity', '0.001', '1000000.01', 'not money'])
def test_invalid_deposits_do_not_advance(value):
    session = Session()
    session.search('48321')
    session.begin()
    assert session.review(value) == 'INVALID_DEPOSIT'
    assert session.stage == Stage.OPENING and session.deposit is None


def test_ineligible_permission_and_session_faults():
    session = Session()
    session.search('77777')
    assert session.begin() == 'MEMBER_INELIGIBLE'
    assert session.review('10') == 'INVALID_STATE'
    session = Session(fault=Fault.PERMISSION_DENIED)
    session.search('48321')
    assert session.begin() == 'PERMISSION_DENIED'
    assert session.counters.opened == 0
    session = Session(fault=Fault.SESSION_EXPIRED)
    assert session.search('48321') == 'SESSION_EXPIRED'
    assert session.begin() == 'INVALID_STATE'


def test_sessions_have_independent_mutation_state():
    first, second = Session(), Session()
    first.search('48321')
    first.begin()
    first.review('10.00')
    first.confirm()
    assert first.counters.opened == 1 and second.counters.opened == 0
    assert second.member is None


def test_condition_template_binding_is_private_and_non_mutating(artifact_data):
    artifact_data['success']['expected'] = {'kind':'text_equals','value':'{{ inputs.member_id }}'}
    artifact = CapabilityArtifact.model_validate(artifact_data)
    bound = bind_conditions(artifact, {'member_id':'fictional-private-key'})
    assert bound.success.expected.value == 'fictional-private-key'
    assert artifact.success.expected.value == '{{ inputs.member_id }}'


@pytest.mark.parametrize('value', ['{{ inputs.unknown }}', '{{ inputs.member_id.upper() }}'])
def test_invalid_condition_templates_rejected(artifact_data, value):
    artifact_data['success']['expected'] = {'kind':'text_equals','value':value}
    with pytest.raises(ValidationError):
        CapabilityArtifact.model_validate(artifact_data)
