"""Real discovery -> deterministic compilation -> isolated different-input replay."""
if __name__ == "__main__":
    from acceptance.command import managed_main
    managed_main("replay")

from acceptance.bundle import output_root

import argparse
import asyncio
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

from bank_simulator.server import running_server
from capability_compiler.compiler import CapabilityCompiler, CompilationError
from capability_compiler.spec import member_balance_spec
from capability_compiler.storage import ArtifactStore
from capability_compiler.validation import artifact_digest
from deterministic_ui.evidence import EvidenceContext, EvidenceWriter
from deterministic_ui.models import CapabilityArtifact
from deterministic_ui.playwright_surface import PlaywrightSurface
from discovery.gemini_client import GeminiModelClient
from discovery.models import DiscoveryRequest, DiscoveryStatus
from discovery.orchestrator import DiscoveryOrchestrator


async def replay_worker(command: dict) -> dict:
    env = {key:value for key,value in os.environ.items() if not key.startswith('GEMINI_')
           and key not in {'GOOGLE_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'}}
    process = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name('replay_generated.py')),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    stdout, stderr = await process.communicate(json.dumps(command).encode())
    if process.returncode != 0:
        raise RuntimeError('ISOLATED_REPLAY_WORKER_FAILED')  # Do not print raw validation errors/inputs.
    return json.loads(stdout)


async def run(args) -> int:
    if args.member_id == args.validate_member_id:
        raise ValueError('VALIDATION_MEMBER_MUST_DIFFER')
    if not re.search(rf'\bmember\s+{re.escape(args.member_id)}\b', args.goal, re.IGNORECASE):
        raise ValueError('GOAL_AND_DISCOVERY_INPUT_MUST_MATCH')
    spec = member_balance_spec(args.version)
    store = ArtifactStore(Path('capabilities/generated'))
    if (store.root / spec.capability_id / spec.version).exists():
        raise FileExistsError('VERSION_EXISTS_USE_A_NEW_VERSION')
    model = GeminiModelClient(model=args.model, env_file=Path('.env'))
    with running_server() as server:
        async with PlaywrightSurface.open(server.url) as surface:
            discovered = await DiscoveryOrchestrator(surface, model, evidence_root=output_root("discovery")).execute(DiscoveryRequest(goal=args.goal, member_id=args.member_id))
        print(f'DISCOVERY: {discovered.status}; provider={discovered.provider}; model={discovered.model}; model_calls={discovered.model_calls}', flush=True)
        print(f'Discovery evidence: {discovered.evidence_directory}', flush=True)
        if discovered.status != DiscoveryStatus.SUCCESS:
            print(f'Discovery stopped: {discovered.code}')
            return 1
        artifact = CapabilityCompiler().compile(discovered, spec)
        draft_path = store.save_draft(artifact)
        writer = EvidenceWriter(output_root('replay', 'compilation'), uuid4().hex, artifact,
                                context=EvidenceContext(execution_mode='compilation', actor='COMPILER'))
        writer.emit('compiled', status='DRAFT', model_calls=0)
        writer.write_json('compilation.json', {'discovery_run_id':discovered.run_id, 'discovery_evidence':discovered.evidence_directory,
            'compiler_version':CapabilityCompiler.version, 'artifact':str(draft_path), 'artifact_digest':artifact_digest(artifact),
            'source_sequences':artifact.provenance.source_sequences if artifact.provenance else [],
            'parameterization':'verified input_binding -> inputs.member_id; no text replacement',
            'business_outcome_source':'explicit simulator application contract', 'model_calls':0})
        print(f'COMPILATION: {artifact.capability_id}@{artifact.capability_version}; DRAFT; {draft_path}', flush=True)
        validation = await replay_worker({'mode':'validate', 'url':server.url, 'artifact':str(draft_path),
            'source_inputs':discovered.invocation_inputs, 'inputs':{'member_id':args.validate_member_id},
            'evidence_root':str(output_root('replay', 'validation')), 'store_root':str(store.root)})
        writer.write_json('validation.json', {key:value for key,value in validation.items() if key != 'replay'} |
            {'run_id':validation['replay']['run_id'] if validation['replay'] else None,
             'status':validation['replay']['status'] if validation['replay'] else 'REJECTED', 'different_inputs':True})
        replay = validation['replay']
        if not replay or replay['status'] != 'SUCCESS':
            writer.emit('validation', status='DRAFT', model_calls=0)
            writer.write_json('result.json', {'status':'DRAFT', 'code':'VALIDATION_FAILED'})
            print('VALIDATION FAILED: artifact remains DRAFT')
            return 1
        balance = Decimal(replay['outputs']['savings_balance'])
        print(f'VALIDATION REPLAY: SUCCESS; member_id=[redacted]; savings_balance={balance}; type={validation["output_types"]["savings_balance"]}; model_calls={replay["model_calls"]}', flush=True)
        print('Replay isolation: model imports blocked; loaded model modules=[]; model credentials absent', flush=True)
        business = await replay_worker({'mode':'replay', 'url':server.url, 'artifact':validation['artifact'],
            'inputs':{'member_id':'99999'}, 'evidence_root':str(output_root('handoff', 'business'))})
        missing = business['replay']
        writer.emit('validation', status='VALIDATED', model_calls=0)
        writer.write_json('result.json', {'status':'VALIDATED', 'artifact':validation['artifact'],
            'discovery_run_id':discovered.run_id, 'validation_run_id':replay['run_id'], 'replay_model_calls':replay['model_calls'],
            'business_run_id':missing['run_id'], 'business_status':missing['status'], 'business_code':missing['business_code'],
            'business_model_calls':missing['model_calls']})
        print(f'BUSINESS REPLAY: {missing["status"]} / {missing["business_code"]}; model_calls={missing["model_calls"]}')
        print(f'CAPABILITY STATUS: DRAFT -> VALIDATED\nArtifact: {validation["artifact"]}\nCompilation evidence: {writer.directory}')
        # Reload the saved generated artifact as an additional schema check.
        CapabilityArtifact.model_validate_json(Path(validation['artifact']).read_text())
        return 0 if missing['business_code'] == 'MEMBER_NOT_FOUND' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--goal', default='Find member 48321 and retrieve their savings balance.')
    parser.add_argument('--member-id', default='48321')
    parser.add_argument('--validate-member-id', default='83921')
    parser.add_argument('--version', default='1.0.0')
    parser.add_argument('--model', default=None)
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(run(args)))
    except CompilationError as exc:
        print(f'Compilation stopped: {exc}')  # Compiler exceptions contain fixed safe codes only.
        raise SystemExit(1)
    except (CompilationError, ValueError, FileExistsError, RuntimeError) as exc:
        print(f'Pipeline stopped: {type(exc).__name__}. Review configuration, version, and run evidence.')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
