import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from bank_simulator.server import running_server
from deterministic_ui.models import CapabilityArtifact, Status
from deterministic_ui.playwright_surface import PlaywrightSurface
from tenant_reuse.models import TenantContext, digest
from tenant_reuse.runner import replay_tenant
from test_tenants import binding, CANONICAL

pytestmark = pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS")!="1",
                               reason="Set RUN_BROWSER_TESTS=1 with Chromium installed")


@pytest.mark.parametrize("tenant,drift,member,version,expected", [
    ("bank_a","none","83921","1",Status.SUCCESS),
    ("bank_b","none","83921","1",Status.SUCCESS),
    ("bank_b","label","83921","1",Status.SUCCESS),
    ("bank_b","structural","83921","1",Status.SUCCESS),
    ("bank_b","ambiguous","83921","1",Status.HUMAN_REQUIRED),
    ("bank_b","none","99999","1",Status.BUSINESS_OUTCOME),
    ("bank_b","none","83921","2",Status.HARD_FAILURE),
])
async def test_real_canonical_cross_tenant_drift(tmp_path,tenant,drift,member,version,expected):
    original = CANONICAL.read_bytes()
    canonical = CapabilityArtifact.model_validate_json(original)
    with running_server() as server:
        ctx=TenantContext(tenant_id=tenant,display_name=tenant,
            base_url=f"{server.url}/?tenant={tenant}&drift={drift}&application_version={version}",
            product="legacy-bank-simulator",application_version="1")
        async with PlaywrightSurface.open(ctx.base_url) as surface:
            result=await replay_tenant(canonical,ctx,binding(tenant),surface,{"member_id":member},
                                       evidence_root=tmp_path)
        assert result.status == expected and result.model_calls == 0
        if expected == Status.SUCCESS:
            assert result.outputs == {"savings_balance":Decimal("807.20")}
        folder=tmp_path/result.run_id
        metadata=json.loads((folder/"metadata.json").read_text())
        assert metadata["canonical_digest"]==digest(canonical)
        assert metadata["tenant_id"]==tenant and metadata["observed_application_version"]==version
        assert metadata["binding_version"]=="1.0.0"
        telemetry=json.loads((folder/"locator-telemetry.json").read_text())
        if drift=="label":
            signals=telemetry["drift_signals"]
            assert any(s["fallback_depth"]==2 and s["strategy_used"]=="css"
                       and s["execution_result"]=="SUCCESS" for s in signals)
        if drift=="structural":
            assert not telemetry["drift_signals"]
        if expected == Status.BUSINESS_OUTCOME:
            assert result.business_code=="MEMBER_NOT_FOUND"
        if expected == Status.HUMAN_REQUIRED:
            assert result.failure is not None
            assert result.failure.code=="AMBIGUOUS_TARGET"
            assert any(s["ambiguity"] and s["match_count"]==2 for s in telemetry["drift_signals"])
        with server.lock:
            assert len(server.sessions)==1
            session=next(iter(server.sessions.values()))
            assert session.counters.search == (0 if drift=="ambiguous" or version=="2" else 1)
            assert session.counters.confirm==0
        assert CANONICAL.read_bytes()==original


async def test_bank_b_without_binding_stops_before_action(tmp_path):
    canonical=CapabilityArtifact.model_validate_json(CANONICAL.read_text())
    with running_server() as server:
        ctx=TenantContext(tenant_id="bank_b",display_name="Bank B",
            base_url=f"{server.url}/?tenant=bank_b",product="legacy-bank-simulator",application_version="1")
        async with PlaywrightSurface.open(ctx.base_url) as surface:
            result=await replay_tenant(canonical,ctx,None,surface,{"member_id":"83921"},evidence_root=tmp_path)
        assert result.failure is not None
        assert result.status==Status.HARD_FAILURE and result.failure.code=="TENANT_BINDING_REQUIRED"
        with server.lock:
            assert next(iter(server.sessions.values())).counters.search==0
