"""Deterministic run packaging. This module never drives UI or changes capabilities."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from uuid import uuid4

from acceptance.privacy import scan

CATEGORIES = ('discovery', 'replay', 'handoff', 'multitenant', 'evaluation')
REQUIRED_CHECKS = ('unit_suite', 'browser_suite', 'type_checks', 'evaluation', 'tenants',
                   'health', 'handoff', 'discovery_handoff', 'recovery', 'live_discovery')
STAGES = {'evals': 'evaluation/raw/evals', 'reuse': 'multitenant/raw/reuse',
          'health': 'multitenant/raw/health', 'handoff': 'handoff/raw/replay',
          'discovery-handoff': 'handoff/raw/discovery', 'recovery': 'handoff/raw/recovery',
          'live': 'discovery/raw/live'}


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path: Path):
    return json.loads(path.read_text())


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        path.chmod(0o600)
        stream.write(json.dumps(value, indent=2) + '\n')


def stage(root: Path, name: str) -> Path:
    return root / STAGES[name]


def output_root(category: str, subdirectory: str = '') -> Path:
    """Command-only routing; raw library writers still respect explicit caller roots."""
    root = os.environ.get('AI_BANK_EVIDENCE_RUN')
    if not root:
        root = 'evidence/runs/unmanaged'  # --help only; executable CLIs enter managed_main first
    return Path(root) / category / 'raw' / subdirectory


def secrets_from_environment():
    values = [v for k, v in os.environ.items() if any(w in k.upper() for w in ('KEY', 'TOKEN', 'PASSWORD', 'SECRET'))]
    if Path('.env').exists():
        values.extend(line.partition('=')[2].strip().strip('"\'') for line in Path('.env').read_text().splitlines()
                      if line.partition('=')[0].strip() in {'GEMINI_API_KEY', 'GOOGLE_API_KEY'})
    return tuple(values)


class EvidenceRunWriter:
    def __init__(self, evidence_root: Path = Path('evidence'), *, run_id: str | None = None,
                 kind: str = 'partial'):
        self.root = evidence_root
        self.run_id = run_id or uuid4().hex
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', self.run_id):
            raise ValueError('INVALID_EVIDENCE_RUN_ID')
        self.directory = self.root / 'runs' / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.started_at = now()
        self.kind = kind
        self.closed = False
        self.materialized: dict[str, str] = {}
        self.imported_sources: dict[str, str] = {}
        self.imported_from: str | None = None
        self.original_completed_at: str | None = None
        for category in CATEGORIES:
            (self.directory / category).mkdir()
        # Interrupted runs are explicitly incomplete and cannot be promoted.
        write(self.directory / 'summary.json', {'run_id': self.run_id, 'source_run_id': self.run_id,
              'started_at': self.started_at, 'completed_at': None, 'overall_status': 'INCOMPLETE', 'kind': kind})
        write(self.directory / 'manifest.json', {'run_id': self.run_id, 'artifacts': []})
        self._readmes()

    def _readmes(self):
        for category in CATEGORIES:
            files = sorted(p for p in (self.directory / category).iterdir() if p.name != 'README.md')
            links = [f'- [{p.name}]({p.name}{"/" if p.is_dir() else ""})' for p in files]
            (self.directory / category / 'README.md').write_text(
                f'# {category.title()}\n\n' + ('\n'.join(links) if links else 'No evidence produced for this category yet.') +
                '\n\n[Run summary](../summary.json) · [Run index](../README.md)\n')
        lines = ['# Acceptance evidence', '', f'Source run: `{self.run_id}`.', '',
                 '[Summary](summary.json) · [Provenance manifest](manifest.json)', '']
        lines += [f'- [{c.title()}]({c}/README.md)' for c in CATEGORIES]
        lines += ['', 'Raw records retain their original run IDs and paths. The manifest maps recorded source paths to bundled files.',
                  'Discovery may use real Gemini; scripted proposals/operators are labeled in their source reports.',
                  'Successful human-assisted discovery is not automatically compiled. Operator actions remain bounded.',
                  'Controlled evaluation/health results are not production reliability probabilities.']
        (self.directory / 'README.md').write_text('\n'.join(lines) + '\n')

    def materialize(self, source: Path, target: str):
        if not source.is_file():
            return
        destination = self.directory / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FileExistsError('EVIDENCE_ALREADY_MATERIALIZED')
        shutil.copyfile(source, destination)
        destination.chmod(0o600)
        self.materialized[target] = source.relative_to(self.directory).as_posix()

    def _export(self):
        live_reports = sorted((self.directory / 'discovery').rglob('report.json'))
        live = next((read(p).get('claims') for p in live_reports if 'claims' in read(p)), {}) or {}
        discoveries = [p for p in (self.directory / 'discovery').rglob('result.json')
                       if read(p).get('provider') in {'gemini', 'mock'}]
        if discoveries:
            result = discoveries[0]
            self.materialize(result, 'discovery/result.json')
            trajectories = sorted(result.parent.glob('trajectory-*.json'))
            if trajectories:
                (self.directory / 'discovery/trajectory.jsonl').write_text(''.join(json.dumps(read(p))+'\n' for p in trajectories))
            events_path = result.parent / 'events.jsonl'
            if events_path.exists():
                events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
                calls = [e for e in events if e.get('kind') in {'model_call', 'model_error'}]
                if calls:
                    (self.directory / 'discovery/model-calls.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in calls))
        for key, target in [('compilation', 'replay/compilation.json'), ('zero_model_replay', 'replay/validation.json'),
                            ('business_outcome', 'handoff/business-outcome.json')]:
            if key in live:
                write(self.directory / target, live[key])
        validations = list(self.directory.glob('discovery/raw/**/validation/*/result.json'))
        if validations:
            self.materialize(validations[0], 'replay/replay-result.json')
        if not (self.directory / 'replay/replay-result.json').exists():
            standalone_results = [p for p in (self.directory / 'replay/raw').rglob('result.json')
                                  if 'compilation' not in p.relative_to(self.directory / 'replay/raw').parts]
            if standalone_results:
                self.materialize(standalone_results[0], 'replay/replay-result.json')
        compilation_records = list((self.directory / 'replay/raw/compilation').glob('*/compilation.json'))
        if compilation_records:
            record = compilation_records[0]
            self.materialize(record, 'replay/compilation.json')
            if (record.parent / 'validation.json').exists():
                self.materialize(record.parent / 'validation.json', 'replay/validation.json')
            # Preserve standalone pipeline lifecycle exactly as the compiler recorded it.
            if (record.parent / 'result.json').exists():
                live['compilation'] = read(record.parent / 'result.json')
            else:
                live['compilation'] = {'status': 'DRAFT', 'evidence': 'replay/compilation.json'}
        for name, target in [('recovery', 'recovery.json'), ('discovery-handoff', 'discovery-handoff.json')]:
            reports = list(stage(self.directory, name).rglob('report.json'))
            if reports:
                self.materialize(reports[0], 'handoff/' + target)
        controls = list(stage(self.directory, 'handoff').rglob('control-summary.json'))
        if controls:
            self.materialize(controls[0], 'handoff/replay-handoff.json')
        tenant_reports = list(stage(self.directory, 'reuse').rglob('scenarios.json'))
        if tenant_reports:
            rows = read(tenant_reports[0])['scenarios']
            names = {('bank_a', 'none'): 'bank-a', ('bank_b', 'none'): 'bank-b',
                     ('bank_b', 'label'): 'label-drift', ('bank_b', 'structural'): 'structural-drift',
                     ('bank_b', 'ambiguous'): 'ambiguous-drift'}
            for row in rows:
                name = names.get((row['tenant_id'], row['drift']))
                if name and row['status'] in {'SUCCESS', 'HUMAN_REQUIRED'}:
                    target = self.directory / 'multitenant' / (name+'.json')
                    if not target.exists():
                        write(target, row)
                    if row['drift'] == 'ambiguous':
                        write(self.directory / 'handoff/ambiguity.json', row)
        health = list(stage(self.directory, 'health').glob('*/derived/successful_drift/**/summary.json'))
        if health:
            self.materialize(health[0], 'multitenant/health.json')
        evaluations = list(stage(self.directory, 'evals').glob('*/summary.json'))
        evaluation = {}
        if evaluations:
            data = read(evaluations[0])
            rows = data['runs']
            evaluation = {'scenarios_total': len(rows), 'scenarios_passed': sum(r['expectation_met'] for r in rows),
                          'scenarios_failed': sum(not r['expectation_met'] for r in rows),
                          'status': 'PASS' if all(r['expectation_met'] for r in rows) else 'FAIL'}
            self.materialize(evaluations[0], 'evaluation/summary.json')
            records = []
            for r in rows:
                records.append({'scenario_id': r['scenario']['id'], 'expected': r['scenario']['expected_status'],
                                'actual': r['metrics']['status'], 'status': 'PASS' if r['expectation_met'] else 'FAIL',
                                'classification': r['analysis']['code'], 'evidence': r['metrics']['evidence_directory']})
            (self.directory / 'evaluation/scenarios.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
        # This is a reference snapshot, not a claim that this command executed it.
        canonical = Path('capabilities/generated/get_member_balance/1.0.0/validated.json')
        if canonical.exists():
            data = read(canonical)
            target = self.directory / 'replay/canonical-capability.json'
            shutil.copyfile(canonical, target)
            write(self.directory / 'replay/capability-reference.json', {
                'relationship': 'referenced_existing', 'authoritative_path': canonical.as_posix(),
                'snapshot': 'canonical-capability.json', 'capability_id': data['capability_id'],
                'capability_version': data['capability_version'], 'original_provenance': data['provenance'],
                'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        generated = list(self.directory.glob('discovery/raw/**/artifacts/*/*/validated.json'))
        if generated:
            artifact = read(generated[0])
            write(self.directory / 'replay/generated-capability-reference.json', {
                'relationship': 'generated_by_source_discovery',
                'authoritative_path': (f"capabilities/generated/{artifact['capability_id']}/{artifact['capability_version']}/validated.json" if str(live.get('compilation', {}).get('evidence', '')).startswith('capabilities/') else None),
                'source_artifact': live.get('compilation', {}).get('evidence'),
                'snapshot': generated[0].relative_to(self.directory).as_posix(),
                'capability_id': artifact['capability_id'], 'capability_version': artifact['capability_version'],
                'original_provenance': artifact['provenance']})
        return live, evaluation, read(discoveries[0]) if discoveries else {}

    def abort(self):
        """Preserve interrupted/export-failed evidence without exposing exception text."""
        if self.closed:
            return
        summary = {'run_id': self.run_id, 'source_run_id': self.run_id, 'kind': self.kind,
                   'started_at': self.started_at, 'completed_at': now(), 'overall_status': 'FAIL',
                   'reason': 'EVIDENCE_PIPELINE_INTERRUPTED', 'eligible_for_current': False}
        (self.directory / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        self._readmes()
        artifacts = [{'path': p.relative_to(self.directory).as_posix(),
                      'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'relationship': 'generated'}
                     for p in sorted(self.directory.rglob('*')) if p.is_file() and p.name != 'manifest.json']
        (self.directory / 'manifest.json').write_text(json.dumps({'run_id': self.run_id, 'artifacts': artifacts}, indent=2)+'\n')
        self.closed = True

    def finish(self, **kwargs):
        if self.closed:
            raise RuntimeError('EVIDENCE_RUN_ALREADY_FINALIZED')
        try:
            return self._finish(**kwargs)
        except Exception:
            self.abort()
            raise

    def _finish(self, *, checks: dict | None = None, claims: list | None = None,
               exit_code: int = 0, independent: dict | None = None, promote: bool = True):
        if self.closed:
            raise RuntimeError('EVIDENCE_RUN_ALREADY_FINALIZED')
        checks, claims = checks or {}, claims or []
        live, evaluation, discovered = self._export()
        if checks or claims:
            write(self.directory / 'evaluation/acceptance.json', {'checks': checks, 'claims': claims,
                                                                'independent': independent})
        self._readmes()
        privacy = scan([p for p in self.directory.rglob('*') if p.is_file()], secrets=secrets_from_environment())
        # Scan result filenames are relative; no host-specific roots are serialized.
        for finding in privacy['findings']:
            finding['file'] = Path(finding['file']).relative_to(self.directory).as_posix()
        write(self.directory / 'evaluation/privacy-scan.json', privacy)
        failed = discovered.get('status') in {'HARD_FAILURE', 'STUCK', 'MAX_STEPS_EXCEEDED'} or exit_code != 0 or privacy['status'] != 'PASS' or any(c.get('status') == 'FAIL' for c in checks.values()) or any(c.get('status') == 'FAIL' for c in claims)
        # Promotion requires complete independently verified acceptance, never a single stage.
        from capability_eval.scenarios import SCENARIOS
        actual_scenarios = list((self.directory / 'evaluation').glob('scenarios.jsonl'))
        ids = {r['scenario_id'] for r in (json.loads(l) for l in actual_scenarios[0].read_text().splitlines())} if actual_scenarios else set()
        full = (self.kind == 'acceptance' and not failed and
                all(checks.get(k, {}).get('status') == 'PASS' for k in REQUIRED_CHECKS) and
                all(live.get(k, {}).get('status') == 'PASS' for k in ('discovery', 'compilation', 'zero_model_replay', 'business_outcome')) and
                live.get('discovery', {}).get('provider') == 'gemini' and
                live.get('zero_model_replay', {}).get('model_calls') == 0 and
                live.get('zero_model_replay', {}).get('different_member') is True and
                live.get('zero_model_replay', {}).get('balance_verified') is True and
                live.get('zero_model_replay', {}).get('identity_verified') is True and
                live.get('zero_model_replay', {}).get('model_credentials_present') is False and
                live.get('zero_model_replay', {}).get('loaded_model_modules') == [] and
                live.get('zero_model_replay', {}).get('model_import_guard') == 'enabled' and
                independent is not None and independent.get('status') == 'PASS' and
                ids == {s.id for s in SCENARIOS} and evaluation.get('scenarios_failed') == 0 and
                all(c.get('status') == 'PASS' for c in claims))
        replay_result = read(self.directory/'replay/replay-result.json') if (self.directory/'replay/replay-result.json').exists() else {}
        def recorded_stage(name, paths):
            if name in checks:
                return checks[name]
            record = next((p for p in paths if p.is_file()), None)
            return {'status': read(record).get('status', 'RECORDED'),
                    'evidence': record.relative_to(self.directory).as_posix()} if record else {'status': 'SKIPPED'}

        summary = {'run_id': self.run_id, 'source_run_id': self.run_id, 'kind': self.kind,
                   'started_at': self.started_at, 'completed_at': self.original_completed_at or now(),
                   'imported_from': self.imported_from, 'overall_status': 'FAIL' if failed else 'PASS' if full else 'PARTIAL',
                   'discovery': live.get('discovery', {'status': discovered.get('status', 'SKIPPED'),
                                  'provider': discovered.get('provider'), 'model_calls': discovered.get('model_calls')}),
                   'compilation': live.get('compilation', {'status': 'SKIPPED'}),
                   'replay': live.get('zero_model_replay', {'status': replay_result.get('status', 'SKIPPED'), 'model_calls': replay_result.get('model_calls')}),
                   'handoff': {name: recorded_stage(name, [self.directory/'handoff'/file]) for name, file in
                               [('handoff', 'replay-handoff.json'), ('discovery_handoff', 'discovery-handoff.json'), ('recovery', 'recovery.json')]},
                   'multitenant': {'tenants': recorded_stage('tenants', stage(self.directory, 'reuse').glob('index/*/result.json')),
                                   'health': recorded_stage('health', [self.directory/'multitenant/health.json'])},
                   'evaluation': evaluation or {'status': 'SKIPPED'}, 'privacy': privacy,
                   'eligible_for_current': bool(full)}
        (self.directory / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        self._readmes()
        artifacts = []
        for p in sorted(self.directory.rglob('*')):
            if not p.is_file() or p.name == 'manifest.json':
                continue
            rel = p.relative_to(self.directory).as_posix()
            metadata = p.parent / 'metadata.json'
            meta = read(metadata) if metadata.is_file() else {}
            artifact_data = read(p) if p.suffix == '.json' else {}
            if isinstance(artifact_data, dict) and 'provenance' in artifact_data:
                meta = {**meta, **{k: artifact_data.get(k) for k in ('capability_id', 'capability_version')}}
            consumed = rel == 'replay/canonical-capability.json'
            artifacts.append({'path': rel, 'category': rel.split('/')[0] if '/' in rel else 'index',
                              'source_execution': meta.get('execution_mode', self.kind),
                              'run_id': meta.get('run_id', self.run_id),
                              'capability_id': meta.get('capability_id'), 'capability_version': meta.get('capability_version'),
                              'relationship': 'referenced_existing' if consumed else 'copied_historical' if rel in self.imported_sources else 'materialized' if rel in self.materialized else 'generated',
                              'original_source': 'capabilities/generated/get_member_balance/1.0.0/validated.json' if consumed else self.imported_sources.get(rel),
                              'source': self.materialized.get(rel, rel),
                              'original_provenance': artifact_data.get('provenance') if isinstance(artifact_data, dict) else None,
                              'recorded_path': p.as_posix() if not p.is_absolute() else str(Path('runs') / self.run_id / rel), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
        (self.directory / 'manifest.json').write_text(json.dumps({'run_id': self.run_id, 'artifacts': artifacts,
            'source_root': str(Path('runs') / self.run_id), 'references': 'Paths are relative to this bundle; recorded_path resolves original runtime references.'}, indent=2)+'\n')
        self.closed = True
        if full and promote:
            self.promote()
        return summary

    def promote(self):
        summary = read(self.directory / 'summary.json')
        if not self.closed or summary.get('overall_status') != 'PASS' or not summary.get('eligible_for_current'):
            raise ValueError('ONLY_FULL_SUCCESS_CAN_BECOME_CURRENT')
        # A relative, atomically replaced link survives a normal repository clone.
        current = self.root / 'current'
        if current.exists() and not current.is_symlink():
            raise ValueError('CURRENT_MUST_BE_MANAGED_LINK')
        if current.is_symlink():
            previous = read(current / 'summary.json')
            if previous['started_at'] > summary['started_at']:
                return
        temporary = self.root / ('.current-' + self.run_id)
        temporary.symlink_to(Path('runs') / self.run_id, target_is_directory=True)
        os.replace(temporary, current)


def resolve_reference(bundle: Path, reference: str) -> Path:
    """Resolve a bundled or original recorded file path after cloning/migration."""
    manifest = read(bundle/'manifest.json')
    for item in manifest['artifacts']:
        if reference in {item['path'], item.get('recorded_path'), item.get('original_source')}:
            result = bundle/item['path']
            if not result.resolve().is_relative_to(bundle.resolve()) or not result.is_file():
                raise ValueError('INVALID_MANIFEST_REFERENCE')
            return result
    raise ValueError('REFERENCE_NOT_BUNDLED')
