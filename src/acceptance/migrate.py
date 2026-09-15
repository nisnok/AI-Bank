"""Import a complete historical acceptance run without modifying its original files."""
import json
from pathlib import Path
import shutil

from acceptance.bundle import EvidenceRunWriter, STAGES, read, stage, write
from acceptance.verify import verify


def import_run(source: Path, evidence_root: Path = Path('evidence')):
    report = read(source/'report.json')
    bundle = EvidenceRunWriter(evidence_root, run_id=source.name, kind='acceptance')
    bundle.imported_from = source.as_posix()
    bundle.original_completed_at = report['created_at']
    times = []
    try:
        for name in STAGES:
            if not (source/name).is_dir():
                continue
            destination = stage(bundle.directory, name)
            shutil.copytree(source/name, destination)
            for p in destination.rglob('*'):
                if not p.is_file():
                    continue
                rel = p.relative_to(bundle.directory).as_posix()
                bundle.imported_sources[rel] = (source/name/p.relative_to(destination)).as_posix()
                if p.name == 'metadata.json' and read(p).get('started_at'):
                    times.append(read(p)['started_at'])
        bundle.started_at = min(times) if times else report['created_at']
        # Project host-specific command strings out of the new summary; original reports remain at source.
        checks = {name: {k:v for k,v in row.items() if k != 'command'} for name,row in report['checks'].items()}
        claims = [{k:v for k,v in row.items() if k != 'command'} for row in report['claims']]
        # Re-evaluate actual copied traces; source paths still resolve at the retained original location.
        independent = verify(bundle.directory)
        write(bundle.directory/'evaluation/import.json', {
            'source_report': str(source/'report.json'), 'relationship':'historical_import',
            'original_completed_at':report['created_at'],
            'omitted_source_aggregates':'Original reports/commands remain in place; copied stage records are byte-identical.'})
        return bundle, bundle.finish(checks=checks, claims=claims, independent=independent)
    except BaseException:
        bundle.abort()
        raise


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--evidence-root',type=Path,default=Path('evidence'))
    args=parser.parse_args()
    bundle, summary=import_run(args.source,args.evidence_root)
    print(f"Imported {bundle.run_id}: {summary['overall_status']}")
