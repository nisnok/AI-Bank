"""Reviewer acceptance coordinator. Real subprocess checks; live Gemini is opt-in."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

from acceptance.privacy import scan
from acceptance.verify import verify


def execute(command, env, timeout=300):
    try:
        result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=timeout)
        # Never persist raw stdout/stderr: failed tests/provider messages may contain values.
        counts=re.findall(r'(\d+ (?:passed|failed|skipped|error)(?:s)?)',result.stdout)
        return {'status':'PASS' if result.returncode==0 else 'FAIL','exit_code':result.returncode,
                'counts':counts[-8:]}
    except subprocess.TimeoutExpired:
        return {'status':'FAIL','reason':'BOUNDED_COMMAND_TIMEOUT'}


def main(args):
    root=args.evidence_root/uuid4().hex
    root.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ)
    env.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(Path('.playwright').resolve()))
    for key in list(env):
        if key.startswith('GEMINI_') or key in {'GOOGLE_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'}:
            del env[key]
    python=sys.executable
    rows=[]
    checks={}

    def run(name,command,*,live=False,browser=False,timeout=300):
        print(f'Checking {name}...',flush=True)
        child_env=dict(os.environ) if live else env.copy()
        child_env.setdefault('PLAYWRIGHT_BROWSERS_PATH',env['PLAYWRIGHT_BROWSERS_PATH'])
        if browser:
            child_env['RUN_BROWSER_TESTS']='1'
        else:
            child_env.pop('RUN_BROWSER_TESTS',None)
        checks[name]=execute(command,child_env,timeout)
        checks[name]['command']=' '.join(command)
        print(f"{name}: {checks[name]['status']}",flush=True)
        return checks[name]['status']

    def row(claim,check,expected,evidence):
        rows.append({'claim':claim,'command':checks[check]['command'],'expected':expected,
                     'evidence':str(evidence),'status':checks[check]['status']})

    run('unit_suite',[python,'-m','pytest','-q'],timeout=180)
    browser_files=sorted(str(p) for p in Path('tests').glob('*browser.py'))+['tests/test_playwright_surface.py']
    run('browser_suite',[python,'-m','pytest','-q',*browser_files],browser=True,timeout=240)
    run('type_checks',[str(Path(python).with_name('pyright'))],timeout=90)
    run('evaluation',[python,'examples/run_evaluation.py','--evidence-root',str(root/'evals')])
    row('Automated evaluation','evaluation','All 13 scenario expectations match; classified failures',root/'evals')
    run('tenants',[python,'examples/replay_tenant.py','--all','--evidence-root',str(root/'reuse')])
    row('H. Multi-tenant reuse','tenants','Bank A and B succeed with unchanged canonical artifact and zero models',root/'reuse')
    row('I. Safe and ambiguous drift','tenants','Unique fallback succeeds; ambiguity stops before search',root/'reuse')
    row('F. Ambiguity','tenants','HUMAN_REQUIRED; ambiguous search submissions = 0',root/'reuse')
    run('health',[python,'examples/run_reliability_eval.py','--evidence-root',str(root/'health')])
    row('J. Capability health','health','Bank A HEALTHY; successful Bank B DEGRADED from telemetry',root/'health')
    run('handoff',[python,'examples/run_handoff.py','--scripted','--evidence-root',str(root/'handoff')])
    row('G. Same-session handoff','handoff','Two mediated actions; no automation during HUMAN; one account created',root/'handoff')
    run('discovery_handoff',[python,'examples/accept_discovery_handoff.py','--evidence-root',str(root/'discovery-handoff')])
    row('Discovery-time same-session handoff','discovery_handoff',
        'Retained page; HUMAN ownership; audited action; verified fresh decision; SUCCESS',root/'discovery-handoff')
    run('recovery',[python,'examples/accept_recovery.py','--evidence-root',str(root/'recovery')])
    row('E. Bounded recovery','recovery','One safe wait retry; one search submission; RECOVERABLE_ERROR',root/'recovery')
    if args.live_discovery:
        run('live_discovery',[python,'examples/accept_discovery.py','--evidence-root',str(root/'live')],live=True)
        path=root/'live/report.json'
        live=json.loads(path.read_text())['claims'] if path.exists() else {}
    else:
        live={}
    for key,claim,expected in (
        ('discovery','A. Real Gemini discovery','Real provider calls; successful verified trajectory'),
        ('compilation','B. Compilation','Actual trajectory; parameterized immutable DRAFT'),
        ('zero_model_replay','C. Different-member zero-LLM replay','Correct identity/balance in isolated worker; zero models'),
        ('business_outcome','D. Business outcome from newly compiled artifact','BUSINESS_OUTCOME / MEMBER_NOT_FOUND')):
        item=live.get(key,{'status':'SKIPPED_WITH_REASON','reason':'LIVE_DISCOVERY_NOT_REQUESTED' if not args.live_discovery else 'LIVE_WORKER_REPORT_MISSING'})
        rows.append({'claim':claim,'command':checks.get('live_discovery',{}).get('command',
            f'{python} examples/run_acceptance.py --live-discovery'),'expected':expected,
            'evidence':item.get('evidence',str(root/'live/report.json')),'status':item['status'],
            'reason':item.get('reason')})
    row('Security browser checks / selective redaction','browser_suite',
        'Pixel masks; visible headings; full-mask fallback; blocked origins; bounded injection',root/'checks.json')
    try:
        independent=verify(root)
    except Exception:
        independent={'status':'FAIL','reason':'SAVED_EVIDENCE_ASSERTION_FAILED'}
    (root/'independent-checks.json').write_text(json.dumps(independent,indent=2)+'\n')
    rows.append({'claim':'Independent saved-evidence verification','command':'acceptance.verify.verify',
                 'expected':'Ownership, fresh checkpoints, shared canonical artifact, health and business semantics',
                 'evidence':str(root/'independent-checks.json'),'status':independent['status']})
    (root/'checks.json').write_text(json.dumps(checks,indent=2)+'\n')
    # Raw current environment is used solely for matching, not serialized.
    secret_values=tuple(value for name,value in os.environ.items()
                        if any(word in name.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD')))
    if Path('.env').exists():
        secret_values+=tuple(line.partition('=')[2].strip().strip('"\'') for line in Path('.env').read_text().splitlines()
                             if line.partition('=')[0].strip() in {'GEMINI_API_KEY','GOOGLE_API_KEY'})
    privacy=scan([p for p in root.rglob('*') if p.is_file()],secrets=secret_values)
    (root/'privacy-scan.json').write_text(json.dumps(privacy,indent=2)+'\n')
    rows.append({'claim':'Evidence secret/PII canary scan','command':'acceptance.privacy.scan',
                 'expected':'No credential values or fictional PII in persisted text',
                 'evidence':str(root/'privacy-scan.json'),'status':privacy['status']})
    report={'created_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'claims':rows,
            'live_discovery_opt_in':args.live_discovery,'source_root':str(root)}
    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['# Reviewer acceptance report','','Executed local simulator / Chromium checks. No mock run is counted as real discovery.','',
           '| Claim | Command | Expected result | Evidence | Status |','|---|---|---|---|---|']
    for item in rows:
        lines.append(f"| {item['claim']} | `{item['command']}` | {item['expected']} | {item['evidence']} | {item['status']} {item.get('reason') or ''} |")
    (root/'README.md').write_text('\n'.join(lines)+'\n')
    print(f'Acceptance report: {root}/report.json',flush=True)
    return 1 if any(item['status']=='FAIL' for item in rows) or any(c['status']=='FAIL' for c in checks.values()) else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-discovery',action='store_true',help='Opt in to real Gemini calls; missing credentials are skipped')
    parser.add_argument('--evidence-root',type=Path,default=Path('evidence/acceptance-local'))
    raise SystemExit(main(parser.parse_args()))
