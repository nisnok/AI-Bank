import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from bank_simulator.server import running_server
from capability_compiler.compiler import CapabilityCompiler
from capability_compiler.spec import member_balance_spec
from capability_compiler.storage import ArtifactStore
from capability_compiler.validation import CapabilityValidator
from deterministic_ui.models import CapabilityLifecycle, Status
from deterministic_ui.playwright_surface import PlaywrightSurface
from deterministic_ui.replay import ReplayEngine
from discovery.mock_client import MockModelClient
from discovery.models import DiscoveryRequest
from discovery.orchestrator import DiscoveryOrchestrator
from test_discovery import scripted

pytestmark = pytest.mark.skipif(os.environ.get('RUN_BROWSER_TESTS') != '1', reason='Set RUN_BROWSER_TESTS=1 with Chromium installed')


async def test_browser_discover_compile_different_input_and_business(tmp_path):
    with running_server() as server:
        client = MockModelClient(scripted)
        async with PlaywrightSurface.open(server.url) as surface:
            source = await DiscoveryOrchestrator(surface, client, evidence_root=tmp_path/'discovery').execute(
                DiscoveryRequest(goal='Find member 48321 and retrieve their savings balance.', member_id='48321'))
        artifact = CapabilityCompiler().compile(source, member_balance_spec())
        assert '48321' not in artifact.model_dump_json(exclude={'provenance'})
        assert '1420.75' not in artifact.model_dump_json(exclude={'provenance'})
        model_calls_after_discovery = client.calls
        async with PlaywrightSurface.open(server.url) as surface:
            validated = await CapabilityValidator().validate(artifact, source.invocation_inputs, {'member_id':'83921'}, surface,
                                                             evidence_root=tmp_path/'validation')
        assert validated.artifact.lifecycle == CapabilityLifecycle.VALIDATED
        assert validated.replay is not None and validated.replay.status == Status.SUCCESS
        assert validated.replay.outputs['savings_balance'] == Decimal('807.20')
        async with PlaywrightSurface.open(server.url) as surface:
            negative = await ReplayEngine(surface, evidence_root=tmp_path/'negative').execute(validated.artifact, {'member_id':'99999'})
        assert negative.status == Status.BUSINESS_OUTCOME and negative.business_code == 'MEMBER_NOT_FOUND'
        assert negative.model_calls == validated.replay.model_calls == 0
        assert client.calls == model_calls_after_discovery
        # Same generated artifact must reject a plausible balance for the wrong record.
        async with PlaywrightSurface.open(server.url+'/?fault=STALE_MEMBER') as surface:
            stale = await ReplayEngine(surface, evidence_root=tmp_path/'stale').execute(validated.artifact, {'member_id':'48321'})
        assert stale.status == Status.RECOVERABLE_ERROR and not stale.outputs
        events = [json.loads(line) for line in (tmp_path/'stale'/stale.run_id/'events.jsonl').read_text().splitlines()]
        assert not any(e.get('action') == 'extract' for e in events)


async def test_fresh_process_validation_cannot_import_models(tmp_path):
    # Exercise the exact isolation worker used by the real demonstration command.
    import asyncio
    import sys
    with running_server() as server:
        async with PlaywrightSurface.open(server.url) as surface:
            source = await DiscoveryOrchestrator(surface, MockModelClient(scripted), evidence_root=tmp_path/'discovery').execute(
                DiscoveryRequest(goal='Find member 48321 and retrieve their savings balance.', member_id='48321'))
        artifact = CapabilityCompiler().compile(source, member_balance_spec())
        store = ArtifactStore(tmp_path/'generated')
        path = store.save_draft(artifact)
        env = {key:value for key,value in os.environ.items() if not key.startswith('GEMINI_')}
        process = await asyncio.create_subprocess_exec(sys.executable,'examples/replay_generated.py',
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=env)
        data = {'mode':'validate','url':server.url,'artifact':str(path),'source_inputs':source.invocation_inputs,
                'inputs':{'member_id':'83921'},'evidence_root':str(tmp_path/'validation'),'store_root':str(store.root)}
        stdout, stderr = await process.communicate(json.dumps(data).encode())
        assert process.returncode == 0, 'Isolated replay worker failed'
        report = json.loads(stdout)
        assert report['model_import_guard'] == 'enabled' and report['loaded_model_modules'] == []
        assert not report['model_credentials_present']
        assert report['replay']['model_calls'] == 0 and report['replay']['status'] == 'SUCCESS'
        assert report['output_types']['savings_balance'] == 'Decimal'
        assert report['replay']['outputs']['savings_balance'] == '807.20'
