"""Wrap standalone demo commands in the same immutable evidence history as acceptance."""
import os
from pathlib import Path
import subprocess
import sys

from acceptance.bundle import EvidenceRunWriter


def managed_main(category: str):
    if Path(sys.argv[0]).name == 'run_demo.py' and any(a in {'--help', '-h'} for a in sys.argv[1:]):
        print('Run the deterministic demo. Optional: --evidence-root DIRECTORY')
        raise SystemExit(0)
    if os.environ.get('AI_BANK_EVIDENCE_MANAGED') == '1' or any(a in {'--help', '-h'} for a in sys.argv[1:]):
        return
    arguments = list(sys.argv[1:])
    evidence_root = Path('evidence')
    for option in ('--evidence-root', '--evidence'):
        if option in arguments:
            i = arguments.index(option)
            evidence_root = Path(arguments[i+1])
            del arguments[i:i+2]
        else:
            matching = next((a for a in arguments if a.startswith(option+'=')), None)
            if matching:
                evidence_root = Path(matching.split('=',1)[1])
                arguments.remove(matching)
    # Relative output references are portable and never expose the machine root.
    if evidence_root.is_absolute():
        try:
            evidence_root = evidence_root.relative_to(Path.cwd())
        except ValueError:
            raise SystemExit('Evidence root must be inside the repository.')
    bundle = EvidenceRunWriter(evidence_root, kind='standalone')
    env = dict(os.environ, AI_BANK_EVIDENCE_MANAGED='1', AI_BANK_EVIDENCE_RUN=str(bundle.directory))
    code = 1
    try:
        code = subprocess.call([sys.executable, sys.argv[0], *arguments], env=env)
    finally:
        summary = bundle.finish(exit_code=code, promote=False)
        print(f"Evidence: {bundle.directory}/README.md ({summary['overall_status']})", flush=True)
    raise SystemExit(code or (1 if summary['overall_status']=='FAIL' else 0))
