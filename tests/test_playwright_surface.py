"""Optional real-browser contract tests: RUN_BROWSER_TESTS=1 pytest."""
import os
from pathlib import Path

import pytest

from deterministic_ui.models import Accessibility, CSS, Expectation, Relative, Status, Text
from deterministic_ui.playwright_surface import PlaywrightSurface
from deterministic_ui.replay import ReplayEngine

pytestmark = pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Set RUN_BROWSER_TESTS=1 with Chromium installed")


async def test_browser_success_and_business_outcome(artifact, tmp_path):
    url = Path("examples/member_portal.html").resolve().as_uri()
    async with PlaywrightSurface.open(url) as surface:
        replay = ReplayEngine(surface, evidence_root=tmp_path)
        result = await replay.execute(artifact, {"member_id":"demo-001"})
        assert result.status == Status.SUCCESS
        assert str(result.outputs["savings_balance"]) == "1234.56"
        missing = await replay.execute(artifact, {"member_id":"unknown"})
        assert missing.status == Status.BUSINESS_OUTCOME


async def test_browser_queries_and_stable_handle(tmp_path):
    html = tmp_path / "portal.html"
    html.write_text('''<html><body>
    <button>Duplicate</button><button>Duplicate</button>
    <section aria-label="Container"><button>Child</button></section>
    <section aria-label="Container"><button>Other</button></section>
    <button id="replace" onclick="this.outerHTML = '<button>Replacement</button>'">Replace</button>
    <p>Visible text</p></body></html>''')
    async with PlaywrightSurface.open(html.as_uri()) as surface:
        assert len((await surface.query(Accessibility(role="button", name="Duplicate"))).targets) == 2
        scoped = await surface.query(Relative(anchor=Accessibility(role="region", name="Container"), role="button", name="Child"))
        assert scoped.ambiguous_scope
        text = (await surface.query(Text(value="Visible text"))).targets[0]
        assert await surface.wait(text, Expectation(kind="text_equals", value="Visible text"), 100)
        button = (await surface.query(CSS(value="#replace"))).targets[0]
        await surface.click(button, 100)
        from deterministic_ui.surface import SurfaceError
        with pytest.raises(SurfaceError):
            await surface.click(button, 100)
