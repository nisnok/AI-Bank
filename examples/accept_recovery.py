"""Verify real bounded recovery against the simulator's delayed response."""
from replay_tenant import BLOCKED
import argparse
import asyncio
import json
from pathlib import Path

from bank_simulator.server import running_server
from deterministic_ui.models import CapabilityArtifact, Status
from deterministic_ui.playwright_surface import PlaywrightSurface
from deterministic_ui.replay import ReplayEngine


async def run(root):
    artifact=CapabilityArtifact.model_validate_json(Path('capabilities/simulator/get_member_balance.json').read_text())
    with running_server() as server:
        async with PlaywrightSurface.open(server.url+'/?fault=SLOW_PAGE') as surface:
            result=await ReplayEngine(surface,evidence_root=root).execute(artifact,{'member_id':'48321'})
        events=[json.loads(line) for line in (root/result.run_id/'events.jsonl').read_text().splitlines()]
        retries=[e for e in events if e['kind']=='retry']
        assert result.status==Status.RECOVERABLE_ERROR and result.failure and result.failure.step_id=='verify_member'
        assert len(retries)==1 and retries[0]['step_id']=='verify_member'
        for step in artifact.steps:
            attempts=[e for e in events if e['kind']=='step_attempt' and e.get('step_id')==step.id]
            assert len(attempts)<=step.retry.max_attempts
            if len(attempts)>1:
                assert step.retry.safe_to_repeat
        session=next(iter(server.sessions.values()))
        assert session.counters.search==1 and session.counters.confirm==0
        report={'status':'PASS','run_id':result.run_id,'result':result.status,'retry_count':1,
                'retried_step':'verify_member','safe_to_repeat':True,'search_submissions':1,'model_calls':result.model_calls}
        (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root',type=Path,required=True)
    asyncio.run(run(parser.parse_args().evidence_root))
