import ast
from decimal import Decimal
from pathlib import Path

import pytest

from capability_compiler.compiler import CapabilityCompiler, CompilationError
from capability_compiler.spec import member_balance_spec
from capability_compiler.storage import ArtifactStore
from capability_compiler.validation import CapabilityValidator
from deterministic_ui.models import CapabilityLifecycle as L, Observation, Status
from deterministic_ui.replay import ReplayEngine
from discovery.models import DiscoveryStatus
from test_discovery import DiscoveryFakeSurface, execute


class CompilerFakeSurface(DiscoveryFakeSurface):
    async def click(self, target, timeout_ms):
        await super().click(target, timeout_ms)
        if self.member_id == '99999':
            self.set_match('text', 'Member not found', 'missing')

    async def observe(self, target=None):
        if target and target.token == 'member':
            return Observation(visible=True, value=self.member_id)
        if target and target.token == 'identity':
            return Observation(visible=True, text='83921' if self.stale else self.member_id)
        return await super().observe(target)


@pytest.fixture
async def successful_discovery(tmp_path):
    return await execute(tmp_path / 'discovery')


@pytest.fixture
async def compiled(successful_discovery):
    return CapabilityCompiler().compile(successful_discovery, member_balance_spec())


def test_compile_is_deterministic_and_parameterized(successful_discovery, compiled):
    assert CapabilityCompiler().compile(successful_discovery, member_balance_spec()) == compiled
    assert compiled.lifecycle == L.DRAFT and not compiled.safety.approved_for_replay
    assert compiled.inputs['member_id'].type == 'string'
    assert compiled.outputs['savings_balance'].type == 'decimal'
    assert [step.action.value for step in compiled.steps] == ['fill','click','extract']
    assert compiled.steps[0].input == '{{ inputs.member_id }}'
    assert compiled.steps[0].postcondition is not None
    assert compiled.steps[0].postcondition.expected.kind == 'value_equals'
    assert compiled.steps[0].postcondition.expected.value == '{{ inputs.member_id }}'
    assert compiled.steps[-1].precondition is not None
    assert compiled.steps[-1].precondition.expected.value == '{{ inputs.member_id }}'
    assert compiled.success.expected.value == '{{ inputs.member_id }}'
    reusable = compiled.model_dump_json(exclude={'provenance'})
    assert '48321' not in reusable and '1234.56' not in reusable
    assert compiled.provenance is not None
    assert compiled.provenance.discovery_run_id == successful_discovery.run_id
    assert compiled.provenance.source_sequences == [1,2,3]
    assert compiled.steps[0].target == successful_discovery.trajectory[0].target


def test_unexecuted_proposals_are_not_compiled(successful_discovery):
    first = successful_discovery.trajectory[0]
    rejected = first.model_copy(update={'sequence':0, 'attempted':False,'executed':False,'verified':False,'compilation_eligible':False})
    result = successful_discovery.model_copy(update={'trajectory':[rejected,*successful_discovery.trajectory]})
    assert len(CapabilityCompiler().compile(result, member_balance_spec()).steps) == 3


def test_search_processing_state_uses_subsequent_identity_observation(successful_discovery):
    trajectory = list(successful_discovery.trajectory)
    trajectory[1] = trajectory[1].model_copy(update={
        'after':Observation(visible=True, text='Processing', elements=[])})
    artifact = CapabilityCompiler().compile(
        successful_discovery.model_copy(update={'trajectory':trajectory}), member_balance_spec())
    assert artifact.steps[1].postcondition is not None
    assert artifact.steps[1].postcondition.expected.value == '{{ inputs.member_id }}'
    assert artifact.steps[2].precondition == artifact.steps[1].postcondition


@pytest.mark.parametrize('field,value', [('status',DiscoveryStatus.HARD_FAILURE), ('trajectory',[]), ('invocation_inputs',{}), ('outputs',{})])
def test_incomplete_discovery_rejected(successful_discovery, field, value):
    with pytest.raises(CompilationError):
        CapabilityCompiler().compile(successful_discovery.model_copy(update={field:value}), member_balance_spec())


@pytest.mark.parametrize('change', ['unexecuted_fill','ambiguous','missing_after','wrong_value','missing_completion'])
def test_invalid_trajectory_rejected(successful_discovery, change):
    steps = list(successful_discovery.trajectory)
    if change == 'unexecuted_fill':
        steps[0] = steps[0].model_copy(update={'executed':False})
    elif change == 'ambiguous':
        assert steps[0].resolution is not None
        steps[0] = steps[0].model_copy(update={'resolution':steps[0].resolution.model_copy(update={'matches':2})})
    elif change == 'missing_after':
        steps[0] = steps[0].model_copy(update={'after':None})
    elif change == 'wrong_value':
        assert steps[0].after is not None
        after = steps[0].after
        steps[0] = steps[0].model_copy(update={'after':after.model_copy(update={'elements':[
            el.model_copy(update={'value':'different'}) for el in after.elements]})})
    else:
        steps = steps[:-1]
    with pytest.raises(CompilationError):
        CapabilityCompiler().compile(successful_discovery.model_copy(update={'trajectory':steps}), member_balance_spec())


async def test_validation_requires_different_input(compiled, successful_discovery, tmp_path):
    surface = CompilerFakeSurface()
    result = await CapabilityValidator().validate(compiled, successful_discovery.invocation_inputs,
                {'member_id':'48321'}, surface, evidence_root=tmp_path)
    assert result.artifact.lifecycle == L.DRAFT and result.replay is None
    assert not result.different_inputs and not surface.actions


async def test_validation_transitions_without_mutating_draft(compiled, successful_discovery, tmp_path):
    store = ArtifactStore(tmp_path / 'artifacts')
    draft_path = store.save_draft(compiled)
    original = draft_path.read_bytes()
    result = await CapabilityValidator().validate(compiled, successful_discovery.invocation_inputs,
                {'member_id':'83921'}, CompilerFakeSurface(), evidence_root=tmp_path / 'validation')
    assert result.artifact.lifecycle == L.VALIDATED
    assert result.replay is not None and result.replay.status == Status.SUCCESS
    assert result.replay.outputs['savings_balance'] == Decimal('1234.56')
    assert result.replay.model_calls == 0
    validated_path = store.record_validation(result)
    assert validated_path.name == 'validated.json'
    assert draft_path.read_bytes() == original and compiled.lifecycle == L.DRAFT
    with pytest.raises(FileExistsError):
        store.save_draft(compiled)
    with pytest.raises(FileExistsError):
        store.record_validation(result)


async def test_failed_validation_leaves_draft(compiled, successful_discovery, tmp_path):
    surface = CompilerFakeSurface()
    surface.matches.clear()
    result = await CapabilityValidator().validate(compiled, successful_discovery.invocation_inputs,
                {'member_id':'83921'}, surface, evidence_root=tmp_path / 'runs')
    assert result.artifact == compiled and result.code == 'VALIDATION_FAILED'
    assert result.replay is not None and result.replay.status != Status.SUCCESS
    store = ArtifactStore(tmp_path / 'artifacts')
    store.save_draft(compiled)
    path = store.record_validation(result)
    assert path.name == 'draft.json'
    assert len(list((path.parent / 'validations').glob('*.json'))) == 1
    assert not (path.parent / 'validated.json').exists()


async def test_draft_blocks_ordinary_replay(compiled, tmp_path):
    surface = CompilerFakeSurface()
    result = await ReplayEngine(surface, evidence_root=tmp_path).execute(compiled, {'member_id':'83921'})
    assert result.status == Status.HUMAN_REQUIRED and not surface.actions


async def test_generated_artifact_business_outcome(compiled, successful_discovery, tmp_path):
    validated = await CapabilityValidator().validate(compiled, successful_discovery.invocation_inputs,
                {'member_id':'83921'}, CompilerFakeSurface(), evidence_root=tmp_path/'validation')
    result = await ReplayEngine(CompilerFakeSurface(), evidence_root=tmp_path/'negative').execute(validated.artifact, {'member_id':'99999'})
    assert result.status == Status.BUSINESS_OUTCOME and result.business_code == 'MEMBER_NOT_FOUND'
    assert result.model_calls == 0


def test_compiler_no_provider_or_browser_imports():
    for name in ('compiler','spec','validation','storage'):
        tree = ast.parse(Path(f'src/capability_compiler/{name}.py').read_text())
        imports = [node.module or '' for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
        assert not any('playwright' in module or 'gemini' in module or 'model_client' in module or 'orchestrator' in module for module in imports)
    # Replay workers may not import any discovery module, even for type annotations.
    for name in ('validation','storage'):
        assert 'from discovery' not in Path(f'src/capability_compiler/{name}.py').read_text()


def test_locator_ladder_preserves_evidence_and_drops_runtime_text(successful_discovery):
    from deterministic_ui.models import CSS, Label, Text
    trajectory = list(successful_discovery.trajectory)
    step = trajectory[2]
    assert step.target is not None
    learned = step.target.model_copy(update={'strategies':[
        *step.target.strategies, Text(value='1234.56'), Label(value='Savings balance'), CSS(value='#balance')
    ]})
    before = step.before.model_copy(update={'elements':[
        el.model_copy(update={'target':learned,'label':'Savings balance'}) if el.id == step.decision.target_id else el
        for el in step.before.elements]})
    trajectory[2] = step.model_copy(update={'target':learned, 'before':before})
    artifact = CapabilityCompiler().compile(successful_discovery.model_copy(update={'trajectory':trajectory}), member_balance_spec())
    assert [strategy.type for strategy in artifact.steps[-1].target.strategies] == ['accessibility','label','css']
    assert artifact.steps[-1].target.strategies[-1].model_dump()['value'] == '#balance'


async def test_scoped_validation_policy_rejects_modified_bound_draft(compiled):
    from capability_compiler.validation import DraftValidationPolicy
    from deterministic_ui.models import Decision
    from deterministic_ui.resolver import LocatorResolver
    from deterministic_ui.templates import bind_conditions
    policy = DraftValidationPolicy(compiled, {'member_id':'83921'})
    bound = bind_conditions(compiled, {'member_id':'83921'})
    resolution = await LocatorResolver().resolve(bound.steps[0].target, CompilerFakeSurface())
    assert policy.evaluate(bound, bound.steps[0], resolution).decision == Decision.ALLOW
    changed = bound.model_copy(update={'description':'different artifact'})
    assert policy.evaluate(changed, changed.steps[0], resolution).decision == Decision.BLOCK
