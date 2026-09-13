"""Scan text evidence without printing matched values. This is not a DLP proof."""
import json
import re
from pathlib import Path

PII_CANARIES = ('48321', '83921', '77777', '99999', 'Fictional Member ALPHA',
                'Fictional Member BETA', 'Fictional Member GAMMA', '1420.75', '807.20',
                '65.00', '500.00', 'SIM-SAV-0001', 'SIM-OPEN-0001')
SECRET_SHAPES = (
    r'AIza[0-9A-Za-z_-]{35}', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    r'Bearer\s+[A-Za-z0-9._~-]{16,}',
    r'(?i)(?:GEMINI_API_KEY|authorization|password|auth_token|session_token|training_session)\s*["\']?\s*[:=]\s*["\']?([A-Za-z0-9_./+-]{12,})',
)


def scan(paths: list[Path], *, secrets: tuple[str, ...] = (), pii: bool = True) -> dict:
    findings = []
    checked = 0
    for path in paths:
        if path.suffix not in {'.json', '.jsonl', '.md', '.txt', '.html', '.py', '.toml', '.yml', '.yaml'}:
            continue
        text = path.read_text(errors='replace')
        checked += 1
        # Scan string values individually so numeric timestamps/durations and hashes
        # cannot accidentally match short fictional canaries. Schema values still count.
        values = [text]
        if path.suffix in {'.json', '.jsonl'}:
            def strings(value):
                if isinstance(value, str):
                    yield value
                elif isinstance(value, dict):
                    for key, child in value.items():
                        if isinstance(child, (int, float)) and not isinstance(child, bool):
                            # Timing/counter telemetry is not a PII value. Numeric business
                            # values in any other field must still be scanned.
                            if key not in {'duration','duration_ms','latency_ms','input_tokens','output_tokens','thinking_tokens'}:
                                yield str(child)
                                yield f'{child:.2f}'
                        else:
                            yield from strings(child)
                elif isinstance(value, list):
                    for child in value:
                        yield from strings(child)
            try:
                records = [json.loads(line) for line in text.splitlines() if line.strip()] if path.suffix == '.jsonl' else [json.loads(text)]
                values = [item for record in records for item in strings(record)]
            except ValueError:
                findings.append({'file':str(path), 'category':'UNPARSEABLE_EVIDENCE'})
        if any(secret and len(secret) >= 8 and secret in text for secret in secrets) or any(re.search(pattern, text) for pattern in SECRET_SHAPES):
            findings.append({'file':str(path), 'category':'SECRET_SHAPE_OR_CANARY'})
        if pii and any(re.search(r'(?<![\w.])' + re.escape(canary) + r'(?![\w.])', value)
                       for value in values for canary in PII_CANARIES):
            findings.append({'file':str(path), 'category':'PII_CANARY'})
    return {'status':'FAIL' if findings else 'PASS', 'files_scanned':checked, 'findings':findings}


def main():
    import argparse
    import os
    import subprocess
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path)
    parser.add_argument('--repository',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not args.evidence and not args.repository:
        parser.error('Select --evidence or --repository')
    secrets=tuple(value for name,value in os.environ.items()
                  if any(word in name.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD')))
    if Path('.env').exists():
        secrets+=tuple(line.partition('=')[2].strip().strip('"\'') for line in Path('.env').read_text().splitlines()
                       if line.partition('=')[0].strip() in {'GEMINI_API_KEY','GOOGLE_API_KEY'})
    results={}
    if args.repository:
        paths=[Path(p) for p in subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],text=True).splitlines()]
        results['repository']=scan([p for p in paths if p.is_file()],secrets=secrets,pii=False)
    if args.evidence:
        results['evidence']=scan([p for p in args.evidence.rglob('*') if p.is_file()],secrets=secrets)
    text=json.dumps(results,indent=2)+'\n'
    if args.output:
        args.output.write_text(text)
    print(text)
    return 1 if any(item['status']=='FAIL' for item in results.values()) else 0


if __name__=='__main__':
    raise SystemExit(main())
