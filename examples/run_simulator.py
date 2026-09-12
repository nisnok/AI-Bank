"""Replay reviewed capabilities against the local simulator using only the Surface port."""
import argparse
import asyncio
from pathlib import Path
from urllib.parse import urlencode

from bank_simulator.domain import Fault
from deterministic_ui.models import CapabilityArtifact, Decision, Risk
from deterministic_ui.playwright_surface import PlaywrightSurface
from deterministic_ui.policy import PolicyConfig, PolicyEngine
from deterministic_ui.replay import ReplayEngine


def preparation_policy() -> PolicyEngine:
    decisions = dict(PolicyConfig().decisions)
    decisions[Risk.IRREVERSIBLE] = Decision.REQUIRE_HUMAN
    return PolicyEngine(PolicyConfig(decisions=decisions))


async def run(args: argparse.Namespace) -> None:
    artifact = CapabilityArtifact.model_validate_json(
        (Path(__file__).resolve().parents[1] / "capabilities" / "simulator" / f"{args.capability}.json").read_text()
    )
    inputs = {"member_id": args.member_id}
    if args.capability == "prepare_new_savings_subaccount":
        inputs["initial_deposit"] = args.initial_deposit
    url = args.url.rstrip('/') + '/?' + urlencode({"fault": args.fault, "variant": args.variant})
    async with PlaywrightSurface.open(url, headless=not args.headed) as surface:
        result = await ReplayEngine(surface, evidence_root=Path(args.evidence), policy=preparation_policy()).execute(artifact, inputs)
        code = result.business_code or (result.failure.code if result.failure else "CHECKPOINT_PASSED")
        print(f"{result.status} / {code}\nEvidence: {args.evidence}/{result.run_id}/result.json")
        if result.outputs:
            print("Typed balance returned in memory; financial values omitted from console and evidence.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capability', choices=['get_member_balance', 'prepare_new_savings_subaccount'])
    parser.add_argument('--member-id', default='48321')
    parser.add_argument('--initial-deposit', default='25.00')
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--fault', choices=list(Fault), default=Fault.NONE)
    parser.add_argument('--variant', choices=['standard', 'fallback'], default='standard')
    parser.add_argument('--evidence', default='evidence')
    parser.add_argument('--headed', action='store_true')
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
