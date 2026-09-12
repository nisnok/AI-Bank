"""A deliberately tiny substitution language: input references, no expressions."""
import re
from decimal import Decimal, InvalidOperation
from collections.abc import Mapping

from .models import CapabilityArtifact, Condition, FieldSpec, Scalar


REFERENCE = re.compile(r"{{\s*inputs\.([a-z][a-z0-9_]*)\s*}}")


class ValueValidationError(ValueError):
    pass


def validate_value(spec: FieldSpec, value: object, *, extracted: bool = False) -> Scalar:
    if spec.type == "string" and isinstance(value, str):
        return value
    if spec.type == "boolean" and type(value) is bool:
        return value
    if spec.type == "integer" and type(value) is int:
        return value
    if spec.type == "decimal" and isinstance(value, (str, Decimal, int)) and type(value) is not bool:
        try:
            number = Decimal(value)
            if number.is_finite():
                return number
        except InvalidOperation:
            pass
    if extracted and isinstance(value, str):
        if spec.type == "integer" and re.fullmatch(r"-?\d+", value):
            return int(value)
        if spec.type == "boolean" and value in ("true", "false"):
            return value == "true"
    raise ValueValidationError("Value does not match its declared type")


def validate_inputs(specs: Mapping[str, FieldSpec], values: Mapping[str, object]) -> dict[str, Scalar]:
    if set(specs) != set(values):
        raise ValueValidationError("Input keys must exactly match the artifact")
    return {key: validate_value(spec, values[key]) for key, spec in specs.items()}


def render(template: str, inputs: Mapping[str, Scalar]) -> str:
    remainder = REFERENCE.sub("", template)
    if "{{" in remainder or "}}" in remainder:
        raise ValueValidationError("Unsupported template expression")

    def substitute(match: re.Match) -> str:
        if match[1] not in inputs:
            raise ValueValidationError("Undeclared input reference")
        value = inputs[match[1]]
        return str(value).lower() if type(value) is bool else str(value)

    return REFERENCE.sub(substitute, template)


def bind_conditions(artifact: CapabilityArtifact, inputs: Mapping[str, Scalar]) -> CapabilityArtifact:
    """Bind expected values in memory; leave reviewed artifacts and evidence value-free."""
    def bind(condition: Condition | None) -> Condition | None:
        if condition is None or condition.expected.value is None:
            return condition
        expected = condition.expected.model_copy(update={"value": render(condition.expected.value, inputs)})
        return condition.model_copy(update={"expected": expected})

    steps = [step.model_copy(update={"precondition": bind(step.precondition),
                                    "postcondition": bind(step.postcondition)}) for step in artifact.steps]
    outcomes = [outcome.model_copy(update={"condition": bind(outcome.condition)}) for outcome in artifact.business_outcomes]
    return artifact.model_copy(update={"steps": steps, "business_outcomes": outcomes, "success": bind(artifact.success)})
