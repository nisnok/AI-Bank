from abc import ABC, abstractmethod

from deterministic_ui.models import Observation
from .models import DiscoveryAction, HistoryItem, ModelReply


class ModelError(Exception):
    """Safe error codes only; never include request/response bodies or credentials."""


class InvalidModelOutput(ModelError):
    pass


class ModelClient(ABC):
    provider: str
    model: str

    @abstractmethod
    async def decide(self, goal: str, observation: Observation, history: list[HistoryItem],
                     available_actions: list[DiscoveryAction]) -> ModelReply: ...
