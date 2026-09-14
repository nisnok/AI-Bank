"""Real model-driven balance discovery; no capability files or ReplayEngine."""
import argparse
import asyncio
from contextlib import nullcontext
from pathlib import Path
import re
from urllib.parse import urlsplit

from bank_simulator.server import running_server
from deterministic_ui.control import SessionController
from deterministic_ui.handoff import HandoffManager
from operator_ui.scenario import discovery_plans
from operator_ui.server import OperatorServer
from deterministic_ui.playwright_surface import PlaywrightSurface
from discovery.gemini_client import GeminiModelClient
from discovery.model_client import ModelError
from discovery.models import DiscoveryLimits, DiscoveryRequest, DiscoveryStatus
from discovery.orchestrator import DiscoveryOrchestrator


async def run(args) -> int:
    match = re.search(r'\bmember\s+(\d{5})\b', args.goal, re.IGNORECASE)
    if not match or not all(word in args.goal.lower() for word in ('savings', 'balance')):
        print('This milestone supports a savings-balance goal containing member followed by a five-digit identifier.')
        return 2
    request = DiscoveryRequest(goal=args.goal, member_id=match[1])
    try:
        model = GeminiModelClient(model=args.model, env_file=Path('.env'))
    except ModelError as exc:
        print(str(exc))  # Adapter emits safe configuration codes only.
        return 2
    if args.url and (urlsplit(args.url).hostname not in {'127.0.0.1', 'localhost'} or urlsplit(args.url).scheme != 'http'):
        print('Discovery is restricted to the local fictional simulator.')
        return 2
    with running_server() if args.url is None else nullcontext(None) as server:
        if server is not None:
            url = server.url
        else:
            url = args.url
        assert isinstance(url, str)
        async with PlaywrightSurface.open(url, headless=not args.headed) as surface:
            limits = DiscoveryLimits(max_decisions=args.max_decisions, max_seconds=args.max_seconds)
            if args.interactive:
                controller = SessionController(surface)
                manager = HandoffManager(controller, discovery_plans())
                async with OperatorServer(manager) as panel:
                    print(f'Operator panel: {panel.url}', flush=True)
                    print('Discovery keeps this session alive for bounded operator takeover.', flush=True)
                    result = await DiscoveryOrchestrator(controller.automation, model, limits=limits,
                        handoff=manager, evidence_root=Path('evidence/discovery')).execute(request)
            else:
                result = await DiscoveryOrchestrator(surface, model, limits=limits,
                    evidence_root=Path('evidence/discovery')).execute(request)
    print(f'{result.status} / {result.code}\nProvider: {result.provider}; model: {result.model}; calls: {result.model_calls}')
    print(f'Tokens: input={result.usage.input_tokens}, output={result.usage.output_tokens}; latency_ms={result.latency_ms}')
    print(f'Evidence: {result.evidence_directory}/result.json')
    print('Runtime inputs and outputs remain redacted in persisted evidence.')
    return 0 if result.status in {DiscoveryStatus.SUCCESS, DiscoveryStatus.BUSINESS_OUTCOME, DiscoveryStatus.HUMAN_REQUIRED} else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--goal', default='Find member 48321 and retrieve their savings balance.')
    parser.add_argument('--url', help='Existing local simulator URL; otherwise start an ephemeral live simulator')
    parser.add_argument('--model', default=None)
    parser.add_argument('--max-decisions', type=int, default=12)
    parser.add_argument('--max-seconds', type=float, default=600, help='Total deadline including operator time (maximum 600)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--interactive', dest='interactive', action='store_true', default=True)
    mode.add_argument('--non-interactive', dest='interactive', action='store_false', help='CI: return HUMAN_REQUIRED and close cleanly')
    parser.add_argument('--headed', action='store_true')
    args = parser.parse_args()
    if args.interactive and args.headed:
        parser.error('Interactive control uses the audited operator panel; --headed requires --non-interactive')
    raise SystemExit(asyncio.run(run(args)))


if __name__ == '__main__':
    main()
