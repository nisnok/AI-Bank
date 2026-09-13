"""Select text proofs and a small screenshot set without modifying source evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def curate(source: Path, destination: Path):
    destination.mkdir(parents=True,exist_ok=False)
    selected=set()
    # Keep complete text for one pipeline, handoff and recovery; aggregate reports
    # plus representative raw runs for repeated tenant/health/evaluation traffic.
    prefixes=['live','live-retry','recovery','handoff']
    for summary in (source/'evals').glob('*/summary.json'):
        for run in json.loads(summary.read_text())['runs']:
            if run['scenario']['id'] in {'happy_path','tenant_label_drift','ambiguous_control','partial_page_load','required_element_missing'}:
                prefixes.append(str(Path(run['metrics']['evidence_directory']).relative_to(source)))
    for manifest in (source/'reuse/tenant-demos').glob('*/scenarios.json'):
        for run in json.loads(manifest.read_text())['scenarios']:
            if run['drift']=='none' and run['status']=='SUCCESS' or run['drift']=='ambiguous':
                prefixes.append(str(Path(run['evidence']).relative_to(source)))
    for manifest in (source/'health').glob('*/evaluation.json'):
        runs=json.loads(manifest.read_text())['runs']
        for run in (runs[0],runs[5],runs[-1]):
            prefixes.append(str((manifest.parent/'runs'/run['run_id']).relative_to(source)))
    for path in source.rglob('*'):
        if not path.is_file() or path.suffix not in {'.json','.jsonl','.md'}:
            continue
        relative=path.relative_to(source)
        parts=relative.parts
        raw_run = 'runs' in parts or ('reuse' in parts and 'tenants' in parts)
        if not raw_run or any(relative.is_relative_to(prefix) for prefix in prefixes):
            selected.add(path)
    images=[]
    for group in ('live/discovery','live-retry/discovery','live-retry/validation','live-retry/business','live/validation','live/business','recovery','handoff'):
        candidates=sorted((source/group).rglob('*.png'))
        if group=='handoff':
            images.extend(p for p in candidates if p.stem in {'final','confirm_open_account','handoff_1','handback_1_1','handback_2_2'})
        elif candidates:
            preferred=[p for p in candidates if p.stem=='final']
            images.append(preferred[0] if preferred else candidates[-1])
    for summary in (source/'evals').glob('*/summary.json'):
        data=json.loads(summary.read_text())
        for run in data['runs']:
            if run['scenario']['id'] in {'happy_path','tenant_label_drift','ambiguous_control','partial_page_load','required_element_missing'}:
                path=Path(run['metrics']['evidence_directory'])/'screenshots/final.png'
                if path.exists():
                    images.append(path)
    # One real full-mask fallback documents fail-closed behavior.
    for manifest in sorted(source.rglob('*.png.json')):
        if json.loads(manifest.read_text()).get('fallback_full_mask'):
            image=manifest.with_suffix('')
            if image.exists():
                images.append(image)
                break
    selected.update(images)
    records=[]
    for path in sorted(selected):
        relative=path.relative_to(source)
        if relative == Path("README.md"):
            relative=Path("initial-run-index.md")
        target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
        records.append({'source':str(path),'archived':str(relative),
                        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (destination/'archive-manifest.json').write_text(json.dumps({'source_root':str(source),
        'files':records,'screenshot_count':len(set(images)),
        'note':'Original source bytes and references preserved. Resolve source-root paths against this archive using archived paths.'},indent=2)+'\n')
    lines=['# Curated acceptance evidence','',
        '[Final reviewed results](reviewed-report.json) · [Initial attempt](report.json) · [Final test/type checks](final-checks.json) · [Final privacy scan](final-privacy-scan.json) · [Source/archive mapping](archive-manifest.json)','',
        'Source JSON/JSONL is copied byte-for-byte. Original paths refer to the ignored local run root; the archive manifest maps them to these retained files. Image manifests for omitted images describe original captures; only the representative images below are included.','',
        '## Representative safe screenshots','']
    for path in images:
        relative=path.relative_to(source)
        lines.append(f'- [{relative}]({relative})')
    (destination/'README.md').write_text('\n'.join(lines)+'\n')
    return len(records),len(set(images))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    print(curate(args.source,args.destination))
