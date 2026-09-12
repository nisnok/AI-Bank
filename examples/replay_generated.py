"""Fresh-process generated-artifact replay. Model imports and credentials are disabled."""
import importlib.abc
import json
import os
from pathlib import Path
import sys


BLOCKED = frozenset({'discovery', 'google', 'openai', 'anthropic'})


class NoModelImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition('.')[0] in BLOCKED:
            raise ImportError('MODEL_IMPORT_FORBIDDEN_IN_REPLAY')
        return None


sys.meta_path.insert(0, NoModelImports())

import asyncio
from capability_compiler.storage import ArtifactStore
from capability_compiler.validation import CapabilityValidator
from deterministic_ui.models import CapabilityArtifact
from deterministic_ui.playwright_surface import PlaywrightSurface
from deterministic_ui.replay import ReplayEngine


async def main():
    command = json.load(sys.stdin)  # Invocation values travel only through an in-memory pipe.
    artifact = CapabilityArtifact.model_validate_json(Path(command['artifact']).read_text())
    async with PlaywrightSurface.open(command['url']) as surface:
        if command['mode'] == 'validate':
            validated = await CapabilityValidator().validate(artifact, command['source_inputs'], command['inputs'], surface,
                                                             evidence_root=Path(command['evidence_root']))
            stored = ArtifactStore(Path(command['store_root'])).record_validation(validated)
            replay = validated.replay
        else:
            replay = await ReplayEngine(surface, evidence_root=Path(command['evidence_root'])).execute(artifact, command['inputs'])
            stored = Path(command['artifact'])
    loaded = [name for name in sys.modules if name.partition('.')[0] in BLOCKED]
    if loaded or 'GEMINI_API_KEY' in os.environ:
        raise RuntimeError('REPLAY_ISOLATION_FAILED')
    report = {'artifact':str(stored), 'replay':replay.model_dump(mode='json') if replay else None,
              'output_types':{name:type(value).__name__ for name,value in replay.outputs.items()} if replay else {},
              'model_import_guard':'enabled', 'loaded_model_modules':loaded,
              'model_credentials_present':False}
    # This stdout is a private pipe to the parent, not persisted evidence.
    print(json.dumps(report))


if __name__ == '__main__':
    asyncio.run(main())
