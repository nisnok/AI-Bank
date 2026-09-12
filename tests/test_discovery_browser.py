"""Browser contract coverage with deterministic decisions; real Gemini uses the opt-in CLI."""
import os
from pathlib import Path

import pytest

from bank_simulator.server import running_server
from deterministic_ui.playwright_surface import PlaywrightSurface
from discovery.mock_client import MockModelClient
from discovery.models import DiscoveryRequest, DiscoveryStatus
from discovery.orchestrator import DiscoveryOrchestrator
from test_discovery import scripted

pytestmark = pytest.mark.skipif(os.environ.get('RUN_BROWSER_TESTS') != '1', reason='Set RUN_BROWSER_TESTS=1 with Chromium installed')


@pytest.mark.parametrize('variant', ['standard','fallback'])
async def test_normalized_browser_discovery(tmp_path, variant):
    with running_server() as server:
        async with PlaywrightSurface.open(server.url + '/?variant=' + variant) as surface:
            observation = await surface.observe()
            assert observation.title and observation.frames[0].title == 'Account opening reference'
            assert any(el.role == 'textbox' for el in observation.elements)
            # The fallback variant legitimately changes the accessible name.
            def decisions(obs, history):
                if variant == 'fallback' and not history:
                    from discovery.models import DiscoveryAction, ModelDecision
                    field = next(el for el in obs.elements if el.name == 'Member Number')
                    return ModelDecision(action=DiscoveryAction.FILL,target_id=field.id,input_binding='member_id',reason='Fill the member number')
                return scripted(obs, history)
            result = await DiscoveryOrchestrator(surface, MockModelClient(decisions), evidence_root=tmp_path).execute(
                DiscoveryRequest(goal='Find member 48321 and retrieve their savings balance.',member_id='48321'))
            assert result.status == DiscoveryStatus.SUCCESS
            assert str(result.outputs['savings_balance']) == '1420.75'
            assert all(step.resolution is not None for step in result.trajectory[:3])
            assert (Path(result.evidence_directory)/'screenshots'/'1.png').exists()
