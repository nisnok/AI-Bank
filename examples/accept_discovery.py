"""Opt-in real Gemini -> compilation -> credential-free worker validation proof."""
import argparse
import asyncio
from decimal import Decimal
import json
from pathlib import Path

from bank_simulator.server import running_server
from capability_compiler.compiler import CapabilityCompiler
from capability_compiler.spec import member_balance_spec
from capability_compiler.storage import ArtifactStore
from deterministic_ui.models import Action, CapabilityLifecycle
from deterministic_ui.playwright_surface import PlaywrightSurface
from discovery.gemini_client import GeminiModelClient
from discovery.model_client import ModelError
from discovery.models import DiscoveryRequest, DiscoveryStatus
from discovery.orchestrator import DiscoveryOrchestrator
from discover_and_compile import replay_worker


async def run(root: Path):
    root.mkdir(parents=True, exist_ok=False)
    report = {'claims':{}}
    claims = report['claims']
    for key in ('discovery','compilation','zero_model_replay','business_outcome'):
        claims[key] = {'status':'SKIPPED_WITH_REASON','reason':'SUCCESSFUL_REAL_DISCOVERY_REQUIRED'}
    try:
        try:
            model = GeminiModelClient(env_file=Path('.env'))
        except ModelError as exc:
            if str(exc) == 'GEMINI_API_KEY_MISSING':
                claims['discovery'] = {'status':'SKIPPED_WITH_REASON','reason':'GEMINI_API_KEY_MISSING'}
                return report
            raise
        with running_server() as server:
            async with PlaywrightSurface.open(server.url) as surface:
                discovered = await DiscoveryOrchestrator(surface,model,evidence_root=root/'discovery').execute(
                    DiscoveryRequest(goal='Find member 48321 and retrieve their savings balance.',member_id='48321'))
            assert discovered.status == DiscoveryStatus.SUCCESS, discovered.code
            assert discovered.provider == 'gemini' and discovered.model_calls > 0
            assert discovered.outputs == {'savings_balance':Decimal('1420.75')}
            assert discovered.trajectory and all(step.actor=='MODEL' for step in discovered.trajectory)
            directory=Path(discovered.evidence_directory)
            metadata=json.loads((directory/'metadata.json').read_text())
            assert metadata['provider']=='gemini' and metadata['model']==discovered.model
            assert list(directory.glob('trajectory-*.json'))
            claims['discovery']={'status':'PASS','evidence':str(directory),'model_calls':discovered.model_calls,
                                 'provider':discovered.provider,'model':discovered.model}
            artifact=CapabilityCompiler().compile(discovered,member_balance_spec('1.0.0'))
            assert artifact.lifecycle==CapabilityLifecycle.DRAFT and not artifact.safety.approved_for_replay
            reusable=artifact.model_dump_json(exclude={'provenance'})
            assert '48321' not in reusable and '1420.75' not in reusable
            assert all(step.input=='{{ inputs.member_id }}' for step in artifact.steps if step.action==Action.FILL)
            assert artifact.provenance and artifact.provenance.discovery_run_id==discovered.run_id
            for step in artifact.steps:
                if step.action==Action.WAIT:
                    continue
                source=next(item for item in discovered.trajectory if step.id==f'discovered_{item.sequence}')
                assert source.verified and source.executed and source.compilation_eligible
                assert source.target and source.resolution
                assert all(strategy in source.target.strategies for strategy in step.target.strategies)
                assert source.target.strategies[source.resolution.attempts[-1].index] in step.target.strategies
            store=ArtifactStore(root/'artifacts')
            draft=store.save_draft(artifact)
            original=draft.read_bytes()
            try:
                store.save_draft(artifact)
            except FileExistsError:
                pass
            else:
                raise AssertionError('IMMUTABILITY_NOT_ENFORCED')
            claims['compilation']={'status':'PASS','evidence':str(draft),'discovery_run_id':discovered.run_id,
                                   'parameterized':True,'observed_strategies_verified':True,'immutable':True}
            validation=await replay_worker({'mode':'validate','url':server.url,'artifact':str(draft),
                'source_inputs':discovered.invocation_inputs,'inputs':{'member_id':'83921'},
                'evidence_root':str(root/'validation'),'store_root':str(store.root)})
            replay=validation['replay']
            assert replay and replay['status']=='SUCCESS' and replay['model_calls']==0
            assert Decimal(replay['outputs']['savings_balance'])==Decimal('807.20')
            assert validation['model_import_guard']=='enabled' and not validation['loaded_model_modules']
            assert not validation['model_credentials_present']
            events=[json.loads(line) for line in (root/'validation'/replay['run_id']/'events.jsonl').read_text().splitlines()]
            assert any(e.get('condition_id')==artifact.success.id and e.get('status')=='satisfied' for e in events)
            assert draft.read_bytes()==original
            claims['zero_model_replay']={'status':'PASS','evidence':str(root/'validation'/replay['run_id']),
                'different_member':True,'identity_verified':True,'balance_verified':True,'model_calls':0,
                'model_credentials_present':False,'loaded_model_modules':[],'model_import_guard':'enabled'}
            missing=await replay_worker({'mode':'replay','url':server.url,'artifact':validation['artifact'],
                'inputs':{'member_id':'99999'},'evidence_root':str(root/'business')})
            result=missing['replay']
            assert result['status']=='BUSINESS_OUTCOME' and result['business_code']=='MEMBER_NOT_FOUND'
            assert result['failure'] is None and result['model_calls']==0
            claims['business_outcome']={'status':'PASS','evidence':str(root/'business'/result['run_id']),
                'business_code':'MEMBER_NOT_FOUND','infrastructure_failure':False,'model_calls':0}
    except Exception as exc:
        next_claim=next((key for key,item in claims.items() if item['status']!='PASS'),'discovery')
        # Exception text can contain Pydantic values or provider responses; omit it.
        claims[next_claim]={'status':'FAIL','reason':type(exc).__name__}
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root',type=Path,required=True)
    args=parser.parse_args()
    result=asyncio.run(run(args.evidence_root))
    print(json.dumps(result,indent=2))
    raise SystemExit(1 if any(c['status']=='FAIL' for c in result['claims'].values()) else 0)
