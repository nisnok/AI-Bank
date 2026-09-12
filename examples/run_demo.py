"""Run from the repository root after installing the package and Chromium."""
import asyncio
from pathlib import Path

from deterministic_ui.models import CapabilityArtifact
from deterministic_ui.playwright_surface import PlaywrightSurface
from deterministic_ui.replay import ReplayEngine


async def main():
    artifact = CapabilityArtifact.model_validate_json(Path("capabilities/get_member_balance.json").read_text())
    async with PlaywrightSurface.open(Path("examples/member_portal.html").resolve().as_uri()) as surface:
        result = await ReplayEngine(surface).execute(artifact, {"member_id": "demo-001"})
        # Deliberately print no runtime inputs/outputs, even for this synthetic demo.
        print(f"{result.status}: evidence/{result.run_id}/result.json")


if __name__ == "__main__":
    asyncio.run(main())
