"""Privacy projection on top of the shared EvidenceWriter; no raw provider payloads."""
import re
from hashlib import sha256

from deterministic_ui.evidence import EvidenceWriter
from deterministic_ui.models import Observation
from .models import DiscoveryRequest, DiscoveryResult, TrajectoryStep


SAFE_LABELS = {'Member ID', 'Member Number', 'Search', 'Savings balance', 'Loaded member identifier',
               'Open New Savings Sub-account', 'Initial deposit', 'Review', 'Confirm / Open Account'}


def project_strategy(strategy: dict) -> dict:
    result = dict(strategy)
    for key in ('name', 'value'):
        if key in result and result[key] not in SAFE_LABELS:
            result[key] = '[redacted]'
    if 'anchor' in result:
        result['anchor'] = project_strategy(result['anchor'])
    return result


class DiscoveryEvidence:
    def __init__(self, writer: EvidenceWriter, request: DiscoveryRequest):
        self.writer = writer
        self.request = request

    def safe_text(self, text: str) -> str:
        text = text.replace(self.request.member_id, '[MEMBER_ID]')
        # Never persist numeric UI values or likely credential tokens.
        text = re.sub(r'\b\d+(?:[.,]\d+)*\b', '[VALUE]', text)
        return re.sub(r'[A-Za-z0-9_-]{24,}', '[TOKEN]', text)

    def observation(self, observation: Observation) -> dict:
        return {'path': '/', 'title': '[redacted]', 'visible_text': '[redacted]',
                'elements': [{'id': el.id, 'role': el.role, 'name': el.name if el.name in SAFE_LABELS else '[redacted]',
                              'kind': el.kind, 'enabled': el.enabled, 'visible': el.visible,
                              'text': '[redacted]', 'value': '[redacted]' if el.value is not None else None}
                             for el in observation.elements],
                'dialog_count': len(observation.dialogs), 'frame_count': len(observation.frames)}

    def record(self, step: TrajectoryStep) -> None:
        decision = step.decision.model_dump(mode='json')
        # Preserve structure and a safe operational reason, not free-form model text.
        decision['reason'] = f"Model proposed {step.decision.action.value} on an observed UI element."
        decision['target_description'] = '[redacted]'
        decision['expected_text'] = '[redacted]' if step.decision.expected_text else None
        if decision['target_id'] not in {el.id for el in step.before.elements}:
            decision['target_id'] = '[unknown]' if decision['target_id'] else None
        target = step.target.model_dump(mode='json') if step.target else None
        if target:
            target['strategies'] = [project_strategy(strategy) for strategy in target['strategies']]
        data = {'sequence': step.sequence, 'actor': step.actor, 'timestamp': step.timestamp.isoformat(),
                'before': self.observation(step.before), 'decision': decision,
                'semantic_target': target,
                'resolution': step.resolution.model_dump(mode='json', exclude={'target'}) if step.resolution else None,
                'attempted': step.attempted, 'executed': step.executed, 'verified': step.verified, 'compilation_eligible': step.compilation_eligible,
                'after': self.observation(step.after) if step.after else None,
                'postcondition': step.postcondition, 'status': step.status,
                'duration_ms': step.duration_ms, 'prior_failures': step.prior_failures}
        self.writer.write_json(f'trajectory-{step.sequence:03d}.json', data)

    def finish(self, result: DiscoveryResult) -> None:
        value = result.model_dump(mode='json', exclude={'trajectory', 'outputs', 'goal'})
        value['goal'] = self.safe_text(result.goal)
        value['outputs'] = {key: {'type': type(output).__name__, 'value': '[redacted]'} for key, output in result.outputs.items()}
        value['trajectory'] = [f'trajectory-{step.sequence:03d}.json' for step in result.trajectory]
        self.writer.write_json('result.json', value)


def fingerprint(observation: Observation) -> str:
    # Used only in memory for loop detection, never persisted as a value fingerprint.
    return sha256(observation.model_dump_json(exclude={'elements': {'__all__': {'target'}}}).encode()).hexdigest()
