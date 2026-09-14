from decimal import Decimal

from deterministic_ui.models import (Action, ArtifactProvenance, CapabilityArtifact, CapabilityLifecycle,
    Condition, Expectation, Observation, ObservedElement, Risk, SafetyMetadata, SemanticTarget, Step)
from deterministic_ui.templates import ValueValidationError, validate_inputs, validate_value
from discovery.models import DiscoveryAction, DiscoveryResult, DiscoveryStatus, TrajectoryStep
from discovery.safety import classify
from .spec import CapabilitySpec


class CompilationError(ValueError):
    """Safe codes only; no raw observation or invocation values."""


class CapabilityCompiler:
    version = '1.0.0'
    _order = {'accessibility':0, 'label':1, 'text':2, 'relative':3, 'css':4}

    def compile(self, discovery_result: DiscoveryResult, capability_spec: CapabilitySpec) -> CapabilityArtifact:
        result, spec = discovery_result, capability_spec
        if result.handoff_occurred or result.human_action_count:
            raise CompilationError('HUMAN_ASSISTED_TRAJECTORY_REQUIRES_REVIEW')
        if result.status != DiscoveryStatus.SUCCESS or not result.trajectory:
            raise CompilationError('SUCCESSFUL_DISCOVERY_REQUIRED')
        if set(spec.inputs) != {'member_id'} or set(spec.outputs) != {'savings_balance'}:
            raise CompilationError('UNSUPPORTED_COMPILATION_CONTRACT')
        if spec.inputs['member_id'].type != 'string' or spec.outputs['savings_balance'].type != 'decimal':
            raise CompilationError('UNSUPPORTED_COMPILATION_CONTRACT')
        try:
            inputs = validate_inputs(spec.inputs, result.invocation_inputs)
            balance = validate_value(spec.outputs['savings_balance'], result.outputs['savings_balance'])
        except (ValueValidationError, KeyError):
            raise CompilationError('INVOCATION_AND_OUTPUT_PROVENANCE_REQUIRED') from None
        member_id = str(inputs['member_id'])
        runtime_values = {member_id, str(balance)}
        sequence = [item.sequence for item in result.trajectory]
        if sequence != sorted(set(sequence)):
            raise CompilationError('INVALID_TRAJECTORY_ORDER')
        completed = result.trajectory[-1]
        if completed.decision.action != DiscoveryAction.COMPLETE or not completed.verified:
            raise CompilationError('VERIFIED_COMPLETION_REQUIRED')
        selected = [item for item in result.trajectory if item.attempted and item.executed and item.verified and item.compilation_eligible]
        if not selected:
            raise CompilationError('NO_VERIFIED_ACTIONS')
        if any(item.decision.action not in {DiscoveryAction.FILL, DiscoveryAction.CLICK, DiscoveryAction.EXTRACT, DiscoveryAction.WAIT} for item in selected):
            raise CompilationError('UNSUPPORTED_VERIFIED_ACTION')
        steps: list[Step] = []
        actions = []
        for position, item in enumerate(selected):
            if item.status != 'VERIFIED' or item.after is None:
                raise CompilationError('MISSING_VERIFICATION_EVIDENCE')
            action = item.decision.action
            actions.append(action)
            step_id = f'discovered_{item.sequence}'
            if action == DiscoveryAction.WAIT:
                identity = self._identity(item.after, spec, member_id, runtime_values)
                steps.append(Step(id=step_id, action=Action.WAIT, target=identity.target,
                                  postcondition=identity, risk=Risk.READ))
                continue
            element = self._verified_element(item)
            target = self._portable_target(element.target, runtime_values)
            assert item.resolution is not None
            used = item.target.strategies[item.resolution.attempts[-1].index] if item.target else None
            if used not in target.strategies:
                raise CompilationError('SUCCESSFUL_LOCATOR_DEPENDS_ON_RUNTIME_VALUE')
            risk = classify(action, element)
            if risk not in {Risk.READ, Risk.REVERSIBLE_WRITE}:
                raise CompilationError('UNSUPPORTED_RISK')
            if action == DiscoveryAction.FILL:
                binding = item.decision.input_binding
                if binding != spec.identity_input:
                    raise CompilationError('UNSUPPORTED_INPUT_BINDING')
                after = [el for el in item.after.elements if el.target == element.target]
                if len(after) != 1 or after[0].value != inputs[binding]:
                    raise CompilationError('INPUT_BINDING_NOT_VERIFIED')
                steps.append(Step(id=step_id, action=Action.FILL, target=target, risk=risk,
                    input=f'{{{{ inputs.{binding} }}}}',
                    precondition=Condition(id='input_visible', target=target),
                    postcondition=Condition(id='input_value_verified', target=target,
                        expected=Expectation(kind='value_equals', value=f'{{{{ inputs.{binding} }}}}'))))
            elif action == DiscoveryAction.CLICK:
                # A verified click may show an intermediate processing state. The
                # next read/wait observation can prove its eventual completion;
                # never borrow evidence across another UI mutation.
                checkpoint = item.after
                following = selected[position + 1] if position + 1 < len(selected) else None
                if following and following.decision.action in {DiscoveryAction.EXTRACT, DiscoveryAction.WAIT}:
                    checkpoint = following.before
                identity = self._identity(checkpoint, spec, member_id, runtime_values)
                steps.append(Step(id=step_id, action=Action.CLICK, target=target, risk=risk,
                                  precondition=Condition(id='search_visible', target=target), postcondition=identity))
            elif action == DiscoveryAction.EXTRACT:
                if item.decision.output != 'savings_balance':
                    raise CompilationError('UNSUPPORTED_OUTPUT_BINDING')
                try:
                    before_value = Decimal(element.text.strip())
                except Exception:
                    raise CompilationError('OUTPUT_NOT_OBSERVED') from None
                if before_value != balance:
                    raise CompilationError('OUTPUT_NOT_VERIFIED')
                before = self._identity(item.before, spec, member_id, runtime_values)
                after = self._identity(item.after, spec, member_id, runtime_values)
                steps.append(Step(id=step_id, action=Action.EXTRACT, target=target, risk=Risk.READ,
                    output='savings_balance', precondition=before, postcondition=after))
        meaningful = [action for action in actions if action != DiscoveryAction.WAIT]
        if meaningful != [DiscoveryAction.FILL, DiscoveryAction.CLICK, DiscoveryAction.EXTRACT]:
            raise CompilationError('UNSUPPORTED_WORKFLOW_SHAPE')
        final_identity = self._identity(completed.before, spec, member_id, runtime_values)
        targets = [step.target for step in steps] + [final_identity.target]
        for step in steps:
            targets.extend(condition.target for condition in (step.precondition, step.postcondition) if condition)
        targets.extend(outcome.condition.target for outcome in spec.business_outcomes)
        features = sorted({strategy.type for target in targets for strategy in target.strategies}, key=self._order.__getitem__)
        artifact = CapabilityArtifact(schema_version='1.0', capability_id=spec.capability_id,
            capability_version=spec.version, name=spec.name, description=spec.description,
            inputs=spec.inputs, outputs=spec.outputs, steps=steps, success=final_identity,
            business_outcomes=spec.business_outcomes, compatibility=spec.application.model_copy(update={'required_features':features}),
            safety=SafetyMetadata(approved_for_replay=False, max_risk=Risk.REVERSIBLE_WRITE,
                                  notes='Draft requires scoped deterministic validation; no human approval is asserted.'),
            lifecycle=CapabilityLifecycle.DRAFT,
            provenance=ArtifactProvenance(discovery_run_id=result.run_id,
                discovery_timestamp=result.trajectory[0].timestamp.isoformat(), provider=result.provider,
                model=result.model, compiler_version=self.version, source_application=spec.application.application,
                source_sequences=[item.sequence for item in selected]))
        # Defense in depth on reusable fields, not a replacement/parameterization algorithm.
        reusable = artifact.model_dump_json(exclude={'provenance'})
        if any(value and value in reusable for value in runtime_values):
            raise CompilationError('RUNTIME_VALUE_IN_REUSABLE_ARTIFACT')
        return artifact

    def _verified_element(self, item: TrajectoryStep) -> ObservedElement:
        elements = [el for el in item.before.elements if el.id == item.decision.target_id]
        resolution = item.resolution
        if (len(elements) != 1 or not elements[0].visible or not elements[0].enabled
            or item.target != elements[0].target or resolution is None or not resolution.succeeded
            or resolution.code != 'RESOLVED' or resolution.matches != 1 or resolution.target is None
            or resolution.quality == 'unresolved' or not resolution.attempts):
            raise CompilationError('INVALID_RESOLUTION_PROVENANCE')
        attempts = resolution.attempts
        if any(a.matches != 0 or a.diagnostic != 'no_match' for a in attempts[:-1]):
            raise CompilationError('INVALID_RESOLUTION_PROVENANCE')
        last = attempts[-1]
        if ([a.index for a in attempts] != list(range(len(attempts))) or last.matches != 1
            or last.diagnostic != 'unique' or last.index >= len(elements[0].target.strategies)
            or resolution.strategy != elements[0].target.strategies[last.index].type):
            raise CompilationError('INVALID_RESOLUTION_PROVENANCE')
        if any(attempt.strategy != elements[0].target.strategies[attempt.index].type for attempt in attempts):
            raise CompilationError('INVALID_RESOLUTION_PROVENANCE')
        return elements[0]

    def _portable_target(self, target: SemanticTarget, runtime_values: set[str]) -> SemanticTarget:
        strategies = []
        for strategy in sorted(target.strategies, key=lambda item: self._order[item.type]):
            encoded = strategy.model_dump_json()
            if any(value and value in encoded for value in runtime_values):
                continue  # Drop value-dependent fallback locators; never rewrite arbitrary strings.
            if strategy not in strategies:
                strategies.append(strategy)
        if not strategies:
            raise CompilationError('NO_PORTABLE_LOCATOR')
        return target.model_copy(update={'strategies':strategies})

    def _identity(self, observation: Observation, spec: CapabilitySpec, member_id: str,
                  runtime_values: set[str]) -> Condition:
        elements = [el for el in observation.elements if el.name == spec.identity_label and el.visible]
        if len(elements) != 1 or elements[0].text.strip() != member_id:
            raise CompilationError('IDENTITY_NOT_VERIFIED')
        return Condition(id='correct_member_loaded', target=self._portable_target(elements[0].target, runtime_values),
                         expected=Expectation(kind='text_equals', value=f'{{{{ inputs.{spec.identity_input} }}}}'))
