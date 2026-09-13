"""One serialized control lease around one retained Surface."""
import asyncio
from enum import StrEnum
from uuid import uuid4

from .surface import Surface, SurfaceError


class ControlOwner(StrEnum):
    AUTOMATION = "AUTOMATION"
    HUMAN = "HUMAN"


class OwnershipError(SurfaceError):
    pass


class SessionController:
    def __init__(self, surface: Surface):
        self._surface = surface
        self.session_id = uuid4().hex
        self.owner = ControlOwner.AUTOMATION
        self.lock = asyncio.Lock()
        self.automation = LeasedSurface(self, ControlOwner.AUTOMATION)
        self.action_counts = {ControlOwner.AUTOMATION: 0, ControlOwner.HUMAN: 0}

    def require(self, owner: ControlOwner):
        if self.owner != owner:
            raise OwnershipError("CONTROL_NOT_OWNED")

    async def invoke(self, owner, method, *args):
        async with self.lock:
            self.require(owner)
            if method in {"click", "fill", "select"}:
                self.action_counts[owner] += 1
            return await getattr(self._surface, method)(*args)


class LeasedSurface(Surface):
    def __init__(self, controller: SessionController, actor: ControlOwner):
        self._controller = controller
        self._actor = actor
        self.features = controller._surface.features
        self.contract_version = controller._surface.contract_version

    async def query(self, strategy):
        return await self._controller.invoke(self._actor, "query", strategy)

    async def observe(self, target=None):
        return await self._controller.invoke(self._actor, "observe", target)

    async def click(self, target, timeout_ms):
        await self._controller.invoke(self._actor, "click", target, timeout_ms)

    async def fill(self, target, value, timeout_ms):
        await self._controller.invoke(self._actor, "fill", target, value, timeout_ms)

    async def select(self, target, value, timeout_ms):
        await self._controller.invoke(self._actor, "select", target, value, timeout_ms)

    async def extract(self, target, timeout_ms):
        return await self._controller.invoke(self._actor, "extract", target, timeout_ms)

    async def wait(self, target, expected, timeout_ms):
        return await self._controller.invoke(self._actor, "wait", target, expected, timeout_ms)

    async def screenshot(self, path):
        return await self._controller.invoke(self._actor, "screenshot", path)

    async def release_targets(self):
        await self._controller.invoke(self._actor, "release_targets")
