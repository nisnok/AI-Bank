from typing import Literal

from pydantic import Field

from deterministic_ui.models import BusinessOutcome, Compatibility, FieldSpec, Model


class CapabilitySpec(Model):
    capability_id: str = Field(default='get_member_balance', pattern=r'^[a-z][a-z0-9_]*$')
    version: str = Field(default='1.0.0', pattern=r'^\d+\.\d+\.\d+$')
    name: str = 'Get verified member savings balance'
    description: str = 'Compiled from verified discovery actions; validates member identity before reading savings.'
    inputs: dict[str, FieldSpec] = Field(default_factory=lambda: {'member_id':FieldSpec(type='string')})
    outputs: dict[str, FieldSpec] = Field(default_factory=lambda: {'savings_balance':FieldSpec(type='decimal')})
    identity_input: Literal['member_id'] = 'member_id'
    identity_label: str = 'Loaded member identifier'
    application: Compatibility = Field(default_factory=lambda: Compatibility(
        application='legacy-bank-simulator', application_version='1', required_features=[]))
    business_outcomes: list[BusinessOutcome] = Field(default_factory=list)


def member_balance_spec(version: str = '1.0.0') -> CapabilitySpec:
    """Application-level negative-outcome contract, not a hand-authored workflow.

    This message is defined by the simulator. It need not appear during a successful
    discovery, so its source is explicitly the application contract.
    """
    return CapabilitySpec(version=version, business_outcomes=[BusinessOutcome.model_validate({
        'code':'MEMBER_NOT_FOUND', 'description':'The simulator has no member for the supplied identifier.',
        'condition':{'id':'member_not_found', 'target':{'concept':'member_not_found',
            'strategies':[{'type':'text','value':'Member not found'}]}, 'expected':{'kind':'visible'}}
    })])
