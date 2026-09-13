import json
import os
from pathlib import Path

import pytest

from bank_simulator.server import running_server
from capability_eval.runner import EvaluationRunner
from capability_eval.scenarios import SCENARIOS
from deterministic_ui.models import CapabilityArtifact
from deterministic_ui.playwright_surface import PlaywrightSurface
from tenant_reuse.models import TenantBinding

pytestmark=pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS")!="1",reason="Set RUN_BROWSER_TESTS=1 with Chromium installed")


async def test_real_evaluation_all_scenarios_classified(tmp_path):
    path=Path("capabilities/generated/get_member_balance/1.0.0/validated.json")
    original=path.read_bytes()
    canonical=CapabilityArtifact.model_validate_json(original)
    bindings={tenant:TenantBinding.model_validate_json(Path(f"tenant_bindings/{tenant}/1.0.0.json").read_text())
              for tenant in ("bank_a","bank_b")}
    with running_server() as server:
        runner=EvaluationRunner(canonical,bindings,server.url,PlaywrightSurface.open,evidence_root=tmp_path)
        summary,folder=await runner.execute(SCENARIOS)
        assert summary.total_runs==len(SCENARIOS)
        assert all(run.expectation_met for run in summary.runs)
        assert summary.model_calls==0 and summary.fallback_recovered_runs==2
        assert summary.most_common_failure=="PAGE_STATE_INVALID"
        data=json.loads((folder/"summary.json").read_text())
        assert data["expectation_pass_rate"]=="1.0000"
        with server.lock:
            ambiguous=[session for session in server.sessions.values() if session.drift.value=="ambiguous"]
            assert len(ambiguous)==1 and ambiguous[0].counters.search==0
    assert path.read_bytes()==original
