"""Synthetic packaging fixtures only; these are never submission execution evidence."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from acceptance.bundle import CATEGORIES, REQUIRED_CHECKS, EvidenceRunWriter, read, stage, write
from capability_eval.scenarios import SCENARIOS


def complete_fixture(bundle):
    claims: dict[str, dict] = {k: {'status': 'PASS'} for k in ('discovery', 'compilation', 'zero_model_replay', 'business_outcome')}
    claims['discovery'].update(provider='gemini', model_calls=4)
    claims['zero_model_replay'].update(model_calls=0, different_member=True, balance_verified=True,
                                     identity_verified=True, model_credentials_present=False, loaded_model_modules=[],
                                     model_import_guard='enabled')
    write(stage(bundle.directory, 'live')/'report.json', {'claims': claims})
    rows=[{'scenario': {'id': s.id, 'expected_status': str(s.expected_status)},
           'metrics': {'status': str(s.expected_status), 'evidence_directory': 'fixture'},
           'analysis': {'code': None}, 'expectation_met': True} for s in SCENARIOS]
    write(stage(bundle.directory, 'evals')/'fixture/summary.json', {'runs': rows})
    return {k: {'status': 'PASS'} for k in REQUIRED_CHECKS}


def test_initial_structure_and_interrupted_run(tmp_path):
    b=EvidenceRunWriter(tmp_path)
    assert all((b.directory/c).is_dir() for c in CATEGORIES)
    assert read(b.directory/'summary.json')['overall_status']=='INCOMPLETE'
    assert read(b.directory/'manifest.json')['artifacts']==[]
    assert (b.directory/'README.md').is_file()
    assert not (tmp_path/'current').exists()


def test_complete_promotes_and_clone_is_portable(tmp_path):
    b=EvidenceRunWriter(tmp_path/'evidence', kind='acceptance')
    checks=complete_fixture(b)
    summary=b.finish(checks=checks, independent={'status':'PASS'})
    assert summary['overall_status']=='PASS'
    assert (b.root/'current').readlink()==Path('runs')/b.run_id
    clone=tmp_path/'clone'
    shutil.copytree(b.root,clone,symlinks=True)
    assert read(clone/'current/summary.json')['source_run_id']==b.run_id
    for row in read(clone/'current/manifest.json')['artifacts']:
        p=clone/'current'/row['path']
        assert p.is_file()
        assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']


def test_failed_and_partial_do_not_replace_current(tmp_path):
    first=EvidenceRunWriter(tmp_path,kind='acceptance');checks=complete_fixture(first)
    first.finish(checks=checks,independent={'status':'PASS'})
    old=(tmp_path/'current').readlink()
    for code in (1,0):
        b=EvidenceRunWriter(tmp_path)
        write(b.directory/'discovery/provider.json',{'status':'PROVIDER_HTTP_503'})
        s=b.finish(exit_code=code)
        assert s['overall_status']==('FAIL' if code else 'PARTIAL')
        assert (b.directory/'discovery/provider.json').is_file()
        assert (tmp_path/'current').readlink()==old
        with pytest.raises(ValueError):b.promote()
    assert {p.name for p in tmp_path.iterdir()}=={'runs','current'}


@pytest.mark.parametrize('missing',REQUIRED_CHECKS)
def test_every_required_stage_gates_promotion(tmp_path,missing):
    b=EvidenceRunWriter(tmp_path,kind='acceptance');checks=complete_fixture(b)
    checks[missing]={'status':'SKIPPED_WITH_REASON'}
    assert b.finish(checks=checks,independent={'status':'PASS'})['overall_status']=='PARTIAL'
    assert not (tmp_path/'current').exists()


def test_scenario_coverage_is_not_a_hardcoded_count(tmp_path):
    b=EvidenceRunWriter(tmp_path,kind='acceptance');checks=complete_fixture(b)
    p=stage(b.directory,'evals')/'fixture/summary.json';data=read(p);data['runs'].pop();p.write_text(json.dumps(data))
    s=b.finish(checks=checks,independent={'status':'PASS'})
    assert s['evaluation']['scenarios_total']==len(SCENARIOS)-1
    assert s['overall_status']=='PARTIAL'


def test_all_scenarios_and_zero_model_assertions_retained(tmp_path):
    b=EvidenceRunWriter(tmp_path,kind='acceptance');checks=complete_fixture(b)
    b.finish(checks=checks,independent={'status':'PASS'})
    rows=[json.loads(l) for l in (b.directory/'evaluation/scenarios.jsonl').read_text().splitlines()]
    assert {r['scenario_id'] for r in rows}=={s.id for s in SCENARIOS}
    replay=read(b.directory/'replay/validation.json')
    assert replay['model_calls']==0 and replay['different_member'] and replay['identity_verified']
    assert replay['loaded_model_modules']==[] and not replay['model_credentials_present']


def test_source_capability_and_screenshot_bytes_unchanged(tmp_path):
    source=Path('capabilities/generated/get_member_balance/1.0.0/validated.json');before=source.read_bytes()
    b=EvidenceRunWriter(tmp_path)
    image=b.directory/'handoff/raw/picture.png';image.parent.mkdir(parents=True);image.write_bytes(b'opaque-test-image')
    write(image.with_suffix('.png.json'),{'policy':'FULL_MASK','fallback_full_mask':True})
    b.finish()
    assert source.read_bytes()==before
    assert (b.directory/'replay/canonical-capability.json').read_bytes()==before
    assert image.read_bytes()==b'opaque-test-image'
    assert read(image.with_suffix('.png.json'))['policy']=='FULL_MASK'
    ref=read(b.directory/'replay/capability-reference.json')
    assert ref['relationship']=='referenced_existing' and ref['original_provenance']==read(source)['provenance']


def test_privacy_prevents_promotion(tmp_path,monkeypatch):
    secret='test-secret-value-for-bundle'
    monkeypatch.setenv('GEMINI_API_KEY',secret)
    b=EvidenceRunWriter(tmp_path,kind='acceptance');checks=complete_fixture(b)
    write(b.directory/'discovery/unsafe.json',{'value':secret})
    s=b.finish(checks=checks,independent={'status':'PASS'})
    assert s['overall_status']=='FAIL' and not (tmp_path/'current').exists()
    for p in [b.directory/'summary.json',b.directory/'manifest.json']:
        assert secret not in p.read_text()


def test_finalized_bundle_rejects_second_finish_and_duplicate_id(tmp_path):
    b=EvidenceRunWriter(tmp_path,run_id='fixed');b.finish()
    with pytest.raises(RuntimeError):b.finish()
    with pytest.raises(FileExistsError):EvidenceRunWriter(tmp_path,run_id='fixed')
    with pytest.raises(ValueError):EvidenceRunWriter(tmp_path,run_id='../escape')


def test_export_error_leaves_failed_manifest(tmp_path):
    b=EvidenceRunWriter(tmp_path)
    p=b.directory/'discovery/result.json';p.write_text('{broken')
    with pytest.raises(ValueError):b.finish()
    assert read(b.directory/'summary.json')['overall_status']=='FAIL'
    assert any(r['path']=='discovery/result.json' for r in read(b.directory/'manifest.json')['artifacts'])
    assert not (tmp_path/'current').exists()


def test_reference_mapping_and_readme_links(tmp_path):
    import re
    from acceptance.bundle import resolve_reference
    b=EvidenceRunWriter(tmp_path)
    p=b.directory/'handoff/raw/old/result.json'
    write(p,{'status':'SUCCESS'})
    b.imported_sources['handoff/raw/old/result.json']='evidence/old/run/result.json'
    b.finish()
    assert resolve_reference(b.directory,'evidence/old/run/result.json')==p
    with pytest.raises(ValueError):resolve_reference(b.directory,'../../outside')
    for page in b.directory.rglob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)',page.read_text()):
            assert (page.parent/target).exists()


def test_older_success_does_not_replace_newer_current(tmp_path):
    newer=EvidenceRunWriter(tmp_path,kind='acceptance');newer.started_at='2026-09-14T12:00:00Z'
    newer.finish(checks=complete_fixture(newer),independent={'status':'PASS'})
    older=EvidenceRunWriter(tmp_path,kind='acceptance');older.started_at='2026-09-13T12:00:00Z'
    older.finish(checks=complete_fixture(older),independent={'status':'PASS'})
    assert (tmp_path/'current').readlink()==Path('runs')/newer.run_id


def test_coordinator_reads_relocated_live_report(tmp_path, monkeypatch):
    import argparse
    import runpy
    coordinator = runpy.run_path('examples/run_acceptance.py')['execute_acceptance']
    monkeypatch.setitem(coordinator.__globals__, 'execute', lambda *a: {'status': 'PASS', 'counts': []})
    monkeypatch.setitem(coordinator.__globals__, 'verify', lambda *a: {'status': 'PASS'})
    b = EvidenceRunWriter(tmp_path, kind='acceptance')
    complete_fixture(b)
    assert coordinator(argparse.Namespace(live_discovery=True), b) == 0
    summary = read(b.directory/'summary.json')
    assert summary['overall_status'] == 'PASS'
    assert summary['handoff']['discovery_handoff']['status'] == 'PASS'
    assert summary['multitenant']['tenants']['status'] == 'PASS'
    assert summary['evaluation']['status'] == 'PASS'


def test_standalone_compilation_and_handoff_are_not_reported_as_skipped(tmp_path):
    b = EvidenceRunWriter(tmp_path, kind='standalone')
    root = b.directory/'replay/raw/compilation/compiler-run'
    write(root/'compilation.json', {'artifact': 'fixture/draft.json'})
    write(root/'result.json', {'status': 'VALIDATED'})
    write(root/'validation.json', {'status': 'SUCCESS', 'different_inputs': True})
    write(b.directory/'replay/raw/validation/replay-run/result.json', {'status': 'SUCCESS', 'model_calls': 0})
    write(stage(b.directory, 'discovery-handoff')/'operator/report.json', {'status': 'PASS'})
    summary = b.finish()
    assert summary['overall_status'] == 'PARTIAL'
    assert summary['compilation']['status'] == 'VALIDATED'
    assert summary['replay']['status'] == 'SUCCESS'
    assert summary['handoff']['discovery_handoff']['status'] == 'PASS'


def test_retained_current_verifies_without_removed_source_tree():
    from acceptance.verify import verify
    assert verify(Path('evidence/current'))['status'] == 'PASS'


def test_canonical_provenance_references_survive_cleanup():
    artifact = read(Path('capabilities/generated/get_member_balance/1.0.0/validated.json'))
    discovery_id = artifact['provenance']['discovery_run_id']
    source = read(Path('evidence/runs')/discovery_id/'discovery/result.json')
    assert source['run_id'] == discovery_id and source['provider'] == 'gemini'
    validation_id = artifact['provenance']['validation_run_id']
    validation = read(Path('capabilities/generated/get_member_balance/1.0.0/validations')/(validation_id+'.json'))
    assert all(Path(ref).is_file() for ref in validation['evidence_refs'])
    assert read(Path('evidence/validation')/validation_id/'result.json')['model_calls'] == 0


def test_future_runs_are_local_until_explicitly_retained():
    import subprocess
    future = 'evidence/runs/future-retention-probe/summary.json'
    selected = str(Path('evidence/current').resolve()/'summary.json')
    result = subprocess.run(['git', 'check-ignore', '--no-index', future, selected], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.splitlines() == [future]
