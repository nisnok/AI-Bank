import asyncio
from time import monotonic

from .evidence import EvidenceWriter
from .models import BusinessOutcome, Condition, Model
from .resolver import LocatorResolver
from .surface import Surface


class ConditionResult(Model):
    satisfied: bool = False
    ambiguous: bool = False
    business_code: str | None = None
    observed: str = "not_satisfied"


class ConditionEvaluator:
    def __init__(self, resolver: LocatorResolver, poll_ms: int = 50):
        self.resolver = resolver
        self.poll_ms = poll_ms

    async def check(self, condition: Condition, surface: Surface, evidence: EvidenceWriter,
                    step_id: str | None) -> ConditionResult:
        resolution = await self.resolver.resolve(condition.target, surface)
        evidence.resolution(resolution, step_id, condition.id)
        if resolution.code == "AMBIGUOUS_TARGET":
            return ConditionResult(ambiguous=True, observed="ambiguous")
        if not resolution.succeeded:
            return ConditionResult(satisfied=condition.expected.kind == "absent", observed="absent")
        observation = await surface.observe(resolution.target)
        expected = condition.expected
        satisfied = (not observation.visible if expected.kind == "absent" else
                     observation.visible and (expected.kind == "visible" or observation.text == expected.value))
        return ConditionResult(satisfied=satisfied, observed="satisfied" if satisfied else "not_satisfied")

    async def wait(self, condition: Condition, outcomes: list[BusinessOutcome], surface: Surface,
                   evidence: EvidenceWriter, step_id: str | None, timeout_ms: int) -> ConditionResult:
        deadline = monotonic() + timeout_ms / 1000
        while True:
            # Business outcomes take precedence over generic success markers.
            for outcome in outcomes:
                checked = await self.check(outcome.condition, surface, evidence, step_id)
                if checked.ambiguous:
                    return checked
                if checked.satisfied:
                    return ConditionResult(business_code=outcome.code, observed="business_outcome")
            checked = await self.check(condition, surface, evidence, step_id)
            if checked.satisfied or checked.ambiguous:
                return checked
            remaining = deadline - monotonic()
            if remaining <= 0:
                return checked
            await asyncio.sleep(min(self.poll_ms / 1000, remaining))
