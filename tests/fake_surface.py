from pathlib import Path
from collections.abc import Awaitable, Callable

from deterministic_ui.models import MatchSet, Observation, TargetRef
from deterministic_ui.surface import Surface, SurfaceTimeout


class FakeSurface(Surface):
    features = frozenset({"accessibility", "label", "text", "relative", "css"})

    def __init__(self):
        self.matches = {}
        self.observations = {}
        self.queries = []
        self.actions = []
        self.member_id = ""
        self.fail_fills = 0
        self.on_click: Callable[[], Awaitable[None]] | None = None
        self.set_match("accessibility", "Member ID", "member")
        self.set_match("accessibility", "Search", "search")
        self.observations["member"] = Observation(visible=True)
        self.observations["search"] = Observation(visible=True)

    def set_match(self, kind, name, *tokens):
        self.matches[(kind, name)] = MatchSet(targets=[TargetRef(token=token) for token in tokens])

    async def query(self, strategy):
        key = (strategy.type, getattr(strategy, "name", getattr(strategy, "value", "")))
        self.queries.append(key)
        return self.matches.get(key, MatchSet())

    async def observe(self, target=None):
        return self.observations.get(target.token if target else "page", Observation(visible=False))

    async def fill(self, target, value, timeout_ms):
        self.actions.append(("fill", target.token, value))
        if self.fail_fills:
            self.fail_fills -= 1
            raise SurfaceTimeout("SECRET provider error never to be logged")
        self.member_id = value

    async def click(self, target, timeout_ms):
        self.actions.append(("click", target.token))
        if self.on_click:
            await self.on_click()
            return
        if self.member_id == "missing-secret":
            self.set_match("text", "Member not found", "missing")
            self.observations["missing"] = Observation(visible=True, text="Member not found")
        else:
            self.set_match("accessibility", "Member details", "details")
            self.set_match("accessibility", "Savings balance", "balance")
            self.observations["details"] = Observation(visible=True, text="Sensitive name")
            self.observations["balance"] = Observation(visible=True, text="1234.56")

    async def extract(self, target, timeout_ms):
        self.actions.append(("extract", target.token))
        return self.observations[target.token].text

    async def wait(self, target, expected, timeout_ms):
        observation = await self.observe(target)
        return observation.visible and (expected.kind == "visible" or observation.text == expected.value)

    async def screenshot(self, path: Path):
        # A valid, entirely synthetic 1x1 PNG; no UI values leave the fake.
        import base64
        path.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII='))
