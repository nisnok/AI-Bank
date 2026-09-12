"""Real model-driven balance discovery; no capability files or ReplayEngine."""
import argparse
import asyncio
from contextlib import nullcontext
from pathlib import Path
import re
from urllib.parse import urlsplit

from bank_simulator.server import running_server
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
            result = await DiscoveryOrchestrator(surface, model, limits=DiscoveryLimits(max_decisions=args.max_decisions),
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
    parser.add_argument('--headed', action='store_true')
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == '__main__':
    main()
