"""Optional replay continuation port; no operator UI or provider dependencies."""
from abc import ABC, abstractmethod
from enum import StrEnum

from .evidence import EvidenceWriter
from .models import CapabilityArtifact, RunResult, Scalar, Step


class ResumeDisposition(StrEnum):
    COMPLETED_STEP = "COMPLETED_STEP"
    RETRY_STEP = "RETRY_STEP"
    STOP = "STOP"


class HandoffHandler(ABC):
    human_action_count = 0
    handoff_occurred = False

    @abstractmethod
    async def resolve(self, artifact: CapabilityArtifact, step: Step, result: RunResult,
                      inputs: dict[str, Scalar], evidence: EvidenceWriter) -> ResumeDisposition: ...

    def finished(self, result: RunResult) -> None:
        pass
