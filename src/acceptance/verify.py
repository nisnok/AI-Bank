"""Independent assertions over saved genuine acceptance evidence."""
import json
from pathlib import Path

from acceptance.bundle import stage, resolve_reference


def read(path):
    return json.loads(path.read_text())


def verify(root: Path) -> dict:
    handoff=next((stage(root,'handoff')).glob('*/events.jsonl'))
    events=[json.loads(line) for line in handoff.read_text().splitlines()]
    sessions={e['session_id'] for e in events if 'session_id' in e}
    assert len(sessions)==1
    taken=[i for i,e in enumerate(events) if e['kind']=='control_transferred']
    returned=[i for i,e in enumerate(events) if e['kind']=='control_returned']
    assert len(taken)==len(returned)==2
    for start,end in zip(taken,returned):
        assert start<end
        assert events[start]['control_owner']=='HUMAN' and events[end]['control_owner']=='AUTOMATION'
        assert not any(e['kind']=='action' and e.get('actor')!='HUMAN' for e in events[start:end])
        fresh=next(i for i in range(end+1,len(events)) if events[i]['kind']=='resume_observation')
        verified=next(i for i in range(fresh+1,len(events)) if events[i]['kind']=='resume_checkpoint_verified')
        assert end<fresh<verified and events[fresh]['status']=='FRESH_OBSERVATION'
    assert any(e['kind']=='resume_checkpoint_verified' and e['step_id']=='confirm_open_account'
               and e['status']=='COMPLETED_STEP' for e in events)
    summary=read(handoff.parent/'control-summary.json')
    assert all(c['automation_actions_during_human_control']==0 for c in summary['ownership_checks'])
    assert len(summary['ownership_checks'])==2
    tenants=read(next((stage(root,'reuse')/'tenant-demos').glob('*/scenarios.json')))['scenarios']
    assert len({(r['capability_id'],r['capability_version'],r['canonical_digest']) for r in tenants})==1
    assert all(r['model_calls']==0 and not r['loaded_model_modules'] for r in tenants)
    assert all(r['search_submissions']==0 for r in tenants if r['drift']=='ambiguous')
    assert any(r['status']=='BUSINESS_OUTCOME' and r['business_code']=='MEMBER_NOT_FOUND' for r in tenants)
    evaluation=read(next((stage(root,'evals')).glob('*/summary.json')))
    assert evaluation['expectation_pass_rate']=='1.0000' and evaluation['model_calls']==0
    assert evaluation['business_outcomes']==1
    assert all(r['analysis']['code'] is None for r in evaluation['runs'] if r['metrics']['status']=='BUSINESS_OUTCOME')
    health=read(next((stage(root,'health')).glob('*/evaluation.json')))
    assert health['canonical_unchanged'] and health['model_calls']==0
    assert all(r['status']=='SUCCESS' for r in health['runs'])
    reference=next(s['summary'] for s in health['snapshots'] if s['stage']=='successful_drift')
    drift=read(Path(reference) if Path(reference).is_file() else resolve_reference(root, reference))
    assert {t['tenant_id']:t['status'] for t in drift['tenant_health']}=={'bank_a':'HEALTHY','bank_b':'DEGRADED'}
    return {'status':'PASS','handoff_session_count':1,'handoff_verified_resumptions':2,
            'completed_irreversible_step_not_repeated':True,'canonical_shared_across_tenants':True,
            'ambiguous_search_submissions':0,'business_outcome_is_not_infrastructure_failure':True,
            'successful_health_runs':len(health['runs']),'bank_a':'HEALTHY','bank_b':'DEGRADED',
            'source_root':str(root)}
