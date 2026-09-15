"""Replay one Bank A-discovered canonical capability across tenants and controlled drift."""
if __name__ == "__main__":
    from acceptance.command import managed_main
    managed_main("multitenant")

from acceptance.bundle import output_root

import importlib.abc
import os
import sys


BLOCKED = frozenset({"discovery", "google", "openai", "anthropic"})


class NoModelImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition(".")[0] in BLOCKED:
            raise ImportError("MODEL_IMPORT_FORBIDDEN_IN_TENANT_REPLAY")
        return None


sys.meta_path.insert(0, NoModelImports())
for key in list(os.environ):
    if key.startswith("GEMINI_") or key in {"GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}:
        del os.environ[key]

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from bank_simulator.server import running_server
from deterministic_ui.evidence import EvidenceWriter
from deterministic_ui.models import CapabilityArtifact, Status
from deterministic_ui.playwright_surface import PlaywrightSurface
from tenant_reuse.models import TenantBinding, TenantContext, digest
from tenant_reuse.runner import replay_tenant


async def run(args):
    canonical_path = Path("capabilities/generated/get_member_balance/1.0.0/validated.json")
    original = canonical_path.read_bytes()
    canonical = CapabilityArtifact.model_validate_json(original)
    scenarios = [("bank_a","none",args.member_id,"1"), ("bank_b","none",args.member_id,"1"),
                 ("bank_b","label",args.member_id,"1"), ("bank_b","structural",args.member_id,"1"),
                 ("bank_b","ambiguous",args.member_id,"1"), ("bank_b","none","99999","1"),
                 ("bank_b","none",args.member_id,"2")] if args.all else [
                     (args.tenant,args.drift,args.member_id,args.application_version)]
    index = EvidenceWriter(args.evidence_root/"tenant-demos", uuid4().hex, canonical)
    index_rows = []
    with running_server() as server:
        for tenant_id, drift, member, version in scenarios:
            tenant = TenantContext(tenant_id=tenant_id, display_name="Bank A" if tenant_id=="bank_a" else "Bank B",
                base_url=f"{server.url}/?tenant={tenant_id}&drift={drift}&application_version={version}",
                product="legacy-bank-simulator", application_version="1")
            binding_path = Path("tenant_bindings")/tenant_id/"1.0.0.json"
            binding = TenantBinding.model_validate_json(binding_path.read_text())
            async with PlaywrightSurface.open(tenant.base_url) as surface:
                result = await replay_tenant(canonical, tenant, binding, surface, {"member_id":member}, evidence_root=args.evidence_root/"tenants")
            folder = args.evidence_root/"tenants"/result.run_id
            telemetry = json.loads((folder/"locator-telemetry.json").read_text())
            signals = telemetry["drift_signals"]
            with server.lock:
                # Count server-observed submissions for the session just created.
                session = list(server.sessions.values())[-1]
                searches = session.counters.search
            if any(name.partition(".")[0] in BLOCKED for name in sys.modules):
                raise RuntimeError("MODEL_MODULE_LOADED")
            expected = (Status.HARD_FAILURE if version!="1" else
                        Status.HUMAN_REQUIRED if drift=="ambiguous" else
                        Status.BUSINESS_OUTCOME if member=="99999" else Status.SUCCESS)
            if result.status != expected:
                raise RuntimeError("UNEXPECTED_SCENARIO_RESULT")
            if drift=="ambiguous" and searches != 0:
                raise RuntimeError("AMBIGUOUS_CONTROL_WAS_CLICKED")
            if drift=="label" and not any(signal["reason"]=="FALLBACK_USED" for signal in signals):
                raise RuntimeError("FALLBACK_EVIDENCE_MISSING")
            row = {"tenant_id":tenant_id, "drift":drift, "application_version":version,
                   "capability_id":canonical.capability_id, "capability_version":canonical.capability_version,
                   "canonical_digest":digest(canonical), "binding":str(binding_path),
                   "status":result.status, "business_code":result.business_code,
                   "failure_code":result.failure.code if result.failure else None,
                   "run_id":result.run_id, "evidence":str(folder), "model_calls":result.model_calls,
                   "model_import_guard":"enabled", "loaded_model_modules":[],
                   "model_credentials_removed":True,
                   "search_submissions":searches, "drift_signal_count":len(signals)}
            index_rows.append(row)
            print(f"{tenant_id} / {drift} / app {version}: {result.status}; {result.business_code or (result.failure.code if result.failure else 'VERIFIED_BALANCE')}; model_calls={result.model_calls}")
            print(f"Canonical: {canonical.capability_id}@{canonical.capability_version}; binding={tenant_id}@{binding.binding_version}; evidence={folder}")
            if signals:
                signal = signals[0]
                print(f"Telemetry: primary={signal['primary_strategy_succeeded']}; used={signal['strategy_used']}; depth={signal['fallback_depth']}; matches={signal['match_count']}; outcome={signal['execution_result']}")
    assert original == canonical_path.read_bytes()
    index.write_json("scenarios.json", {"canonical":str(canonical_path), "scenarios":index_rows})
    index.write_json("result.json", {"status":"SUCCESS", "scenario_count":len(index_rows), "canonical_unchanged":True})
    rows = ["# Tenant reuse acceptance evidence", "", "Generated by real browser execution; no model calls.", "",
            "| Tenant | Drift | App version | Result | Signals | Evidence |",
            "|---|---|---|---|---|---|"]
    for row in index_rows:
        rows.append(f"| {row['tenant_id']} | {row['drift']} | {row['application_version']} | {row['status']} | {row['drift_signal_count']} | [{row['run_id']}](../../tenants/{row['run_id']}/result.json) |")
    (index.directory/"README.md").write_text("\n".join(rows)+"\n")
    print(f"Reviewer index: {index.directory}/README.md")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=output_root("multitenant", "reuse"))
    parser.add_argument("--tenant", choices=["bank_a","bank_b"], default="bank_a")
    parser.add_argument("--drift", choices=["none","label","structural","ambiguous"], default="none")
    parser.add_argument("--member-id", default="83921")
    parser.add_argument("--application-version", choices=["1","2"], default="1")
    parser.add_argument("--all", action="store_true", help="Run all seven acceptance scenarios")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
