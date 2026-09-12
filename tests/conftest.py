import json
from pathlib import Path

import pytest

from deterministic_ui.models import CapabilityArtifact
from fake_surface import FakeSurface


@pytest.fixture
def artifact_data():
    return json.loads(Path("capabilities/get_member_balance.json").read_text())


@pytest.fixture
def artifact(artifact_data):
    return CapabilityArtifact.model_validate(artifact_data)


@pytest.fixture
def surface():
    return FakeSurface()
