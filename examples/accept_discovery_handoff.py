"""Bounded discovery handoff on real Chromium. Gemini is separately opt-in."""
import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from acceptance.discovery_handoff import exercise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Use real Gemini instead of labeled scripted proposals')
    parser.add_argument('--evidence-root',type=Path,default=Path('evidence/discovery-handoff'))
    args=parser.parse_args()
    root=args.evidence_root/uuid4().hex
    result=asyncio.run(exercise(root,live=args.live))
    print(f"Discovery handoff: {result['status']}; provider={result['provider']}; model_calls={result['model_calls']}")
    print(f'Evidence: {root}/report.json')
