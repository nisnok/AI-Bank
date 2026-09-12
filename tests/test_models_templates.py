from decimal import Decimal

import pytest
from pydantic import ValidationError

from deterministic_ui.models import CapabilityArtifact, FieldSpec
from deterministic_ui.templates import ValueValidationError, render, validate_inputs, validate_value


def test_artifact_roundtrip(artifact):
    assert CapabilityArtifact.model_validate_json(artifact.model_dump_json()) == artifact


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(schema_version="2.0"),
    lambda d: d.update(unexpected=True),
    lambda d: d["steps"][0].update(action="eval"),
    lambda d: d["steps"][0].update(input="{{ inputs.unknown }}"),
    lambda d: d["steps"][0].update(input="{{ 1 + 2 }}"),
    lambda d: d["steps"][0].update(timeout_ms=0),
    lambda d: d["steps"][0].update(retry={"max_attempts":10,"safe_to_repeat":True}),
    lambda d: d["steps"][0].update(retry={"max_attempts":2}),
    lambda d: d["steps"][1].update(id="enter_member_id"),
    lambda d: d["steps"][2].update(output="undeclared"),
    lambda d: d["steps"][0].update(risk="READ"),
    lambda d: d["steps"][0]["target"]["strategies"].reverse(),
])
def test_invalid_artifact(artifact_data, mutation):
    mutation(artifact_data)
    with pytest.raises(ValidationError):
        CapabilityArtifact.model_validate(artifact_data)


@pytest.mark.parametrize('inputs', [{}, {"member_id":42}, {"member_id":True}, {"member_id":"a","extra":"b"}])
def test_typed_input_rejection(artifact, inputs):
    with pytest.raises(ValueValidationError):
        validate_inputs(artifact.inputs, inputs)


def test_typed_values_and_templates(artifact):
    inputs = validate_inputs(artifact.inputs, {"member_id":"000123"})
    assert render("Member {{ inputs.member_id }}", inputs) == "Member 000123"
    assert render("{{inputs.member_id}}", {"member_id":"{{ unsafe }}"}) == "{{ unsafe }}"
    assert validate_value(FieldSpec(type="decimal"), "10.20") == Decimal("10.20")
    assert validate_value(FieldSpec(type="integer"), "12", extracted=True) == 12
    assert validate_value(FieldSpec(type="boolean"), "false", extracted=True) is False


@pytest.mark.parametrize('template', ['{{ inputs.missing }}', '{{ inputs.member_id.upper() }}', '{{ arbitrary }}'])
def test_invalid_template(template):
    with pytest.raises(ValueValidationError):
        render(template, {"member_id":"secret"})


@pytest.mark.parametrize('value', ["NaN", "Infinity", "1,234.50", "$12", 0.1, True])
def test_decimal_is_explicit_and_finite(value):
    with pytest.raises(ValueValidationError):
        validate_value(FieldSpec(type="decimal"), value)
