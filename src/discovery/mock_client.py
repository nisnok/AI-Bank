from collections.abc import Callable

from deterministic_ui.models import Observation
from .model_client import ModelClient, ModelError
from .models import DiscoveryAction, HistoryItem, ModelDecision, ModelReply


class MockModelClient(ModelClient):
    provider = "mock"
    model = "scripted-decisions"

    def __init__(self, decisions: list[ModelDecision] | Callable[[Observation, list[HistoryItem]], ModelDecision]):
        self.decisions = decisions
        self.calls = 0

    async def decide(self, goal: str, observation: Observation, history: list[HistoryItem],
                     available_actions: list[DiscoveryAction]) -> ModelReply:
        index = self.calls
        self.calls += 1
        if callable(self.decisions):
            return ModelReply(decision=self.decisions(observation, history))
        if index >= len(self.decisions):
            raise ModelError("MOCK_EXHAUSTED")
        return ModelReply(decision=self.decisions[index])
