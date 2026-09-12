"""Port implemented by browser or future desktop providers."""
from abc import ABC, abstractmethod
from pathlib import Path

from .models import Expectation, MatchSet, Observation, Strategy, TargetRef


class SurfaceError(Exception):
    """Provider failures are translated at this boundary; messages are never logged."""


class SurfaceTimeout(SurfaceError):
    pass


class Surface(ABC):
    contract_version = "1"
    features: frozenset[str] = frozenset()

    @abstractmethod
    async def query(self, strategy: Strategy) -> MatchSet: ...

    @abstractmethod
    async def observe(self, target: TargetRef | None = None) -> Observation: ...

    @abstractmethod
    async def click(self, target: TargetRef, timeout_ms: int) -> None: ...

    @abstractmethod
    async def fill(self, target: TargetRef, value: str, timeout_ms: int) -> None: ...

    @abstractmethod
    async def extract(self, target: TargetRef, timeout_ms: int) -> str: ...

    @abstractmethod
    async def wait(self, target: TargetRef, expected: Expectation, timeout_ms: int) -> bool: ...

    @abstractmethod
    async def screenshot(self, path: Path) -> None:
        """Write a privacy-safe screenshot; never capture unmasked UI content."""

    async def release_targets(self) -> None:
        """Release run-scoped handles. Engine serializes runs on its surface."""
