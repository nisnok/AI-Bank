"""Exclusive-create, file-backed lifecycle snapshots; no version is overwritten."""
import json
from pathlib import Path

from deterministic_ui.models import CapabilityArtifact, CapabilityLifecycle, Status
from .validation import ValidationResult, artifact_digest


class ArtifactStore:
    def __init__(self, root: Path = Path('capabilities/generated')):
        self.root = root

    def directory(self, artifact: CapabilityArtifact) -> Path:
        return self.root / artifact.capability_id / artifact.capability_version

    def save_draft(self, artifact: CapabilityArtifact) -> Path:
        if artifact.lifecycle != CapabilityLifecycle.DRAFT:
            raise ValueError('DRAFT_REQUIRED')
        directory = self.directory(artifact)
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / 'draft.json'
        self._write(path, artifact.model_dump_json(indent=2))
        return path

    def record_validation(self, result: ValidationResult) -> Path:
        directory = self.directory(result.artifact)
        original = CapabilityArtifact.model_validate_json((directory / 'draft.json').read_text())
        if artifact_digest(original) != result.draft_digest:
            raise ValueError('DRAFT_DIGEST_MISMATCH')
        # The transition may add validation provenance, but never change workflow meaning.
        candidate = result.artifact.model_copy(update={'lifecycle':CapabilityLifecycle.DRAFT,
                                                      'provenance':original.provenance})
        if candidate != original:
            raise ValueError('VALIDATION_CHANGED_ARTIFACT')
        records = directory / 'validations'
        records.mkdir(exist_ok=True)
        run_id = result.replay.run_id if result.replay else 'rejected-same-input'
        record = records / f'{run_id}.json'
        self._write(record, json.dumps({
            'code':result.code, 'different_inputs':result.different_inputs,
            'draft_digest':result.draft_digest, 'replay_run_id':result.replay.run_id if result.replay else None,
            'replay_status':result.replay.status if result.replay else None,
            'model_calls':result.replay.model_calls if result.replay else 0,
            'evidence_refs':result.replay.evidence_refs if result.replay else [],
        }, indent=2))
        if result.artifact.lifecycle == CapabilityLifecycle.VALIDATED:
            if not result.different_inputs or result.replay is None or result.replay.status != Status.SUCCESS:
                raise ValueError('SUCCESSFUL_DIFFERENT_INPUT_REPLAY_REQUIRED')
            path = directory / 'validated.json'
            self._write(path, result.artifact.model_dump_json(indent=2))
            return path
        return directory / 'draft.json'

    @staticmethod
    def _write(path: Path, content: str) -> None:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(content + '\n')
