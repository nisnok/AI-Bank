"""Only this module may import or retain Playwright objects."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic
from uuid import uuid4
from urllib.parse import urlsplit

from playwright.async_api import ElementHandle, Error, Locator, Page, TimeoutError as BrowserTimeout, async_playwright

from .models import Anchor, Expectation, FrameInfo, MatchSet, Observation, ObservedElement, SemanticTarget, Strategy, TargetRef
from .surface import Surface, SurfaceError, SurfaceTimeout


@asynccontextmanager
async def _translate_errors():
    try:
        yield
    except BrowserTimeout as exc:
        raise SurfaceTimeout("UI operation timed out") from exc
    except Error as exc:
        raise SurfaceError("UI provider operation failed") from exc


class PlaywrightSurface(Surface):
    features = frozenset({"accessibility", "label", "text", "relative", "css", "select"})

    def __init__(self, page: Page):
        # Internal use only; public callers use open(), which yields a Surface.
        self._page = page
        self._handles: dict[str, ElementHandle] = {}

    @classmethod
    @asynccontextmanager
    async def open(cls, url: str, *, headless: bool = True):
        async with _translate_errors():
            async with async_playwright() as provider:
                browser = await provider.chromium.launch(headless=headless)
                try:
                    context = await browser.new_context()
                    page = await context.new_page()
                    await page.goto(url, wait_until="domcontentloaded")
                    yield cls(page)
                finally:
                    await browser.close()

    def _locator(self, strategy: Anchor, root: Page | Locator | None = None) -> Locator:
        root = self._page if root is None else root
        if strategy.type == "accessibility":
            return root.get_by_role(strategy.role, name=strategy.name, exact=True)
        if strategy.type == "label":
            return root.get_by_label(strategy.value, exact=True)
        if strategy.type == "text":
            return root.get_by_text(strategy.value, exact=True)
        if strategy.type == "css":
            return root.locator(strategy.value)
        raise SurfaceError("Unsupported strategy")

    async def _visible_handles(self, locator):
        handles = await locator.element_handles()
        visible = []
        for handle in handles:
            if await handle.is_visible():
                visible.append(handle)
            else:
                await handle.dispose()
        return visible

    async def query(self, strategy: Strategy) -> MatchSet:
        async with _translate_errors():
            anchor: Locator | None = None
            if strategy.type == "relative":
                anchor = self._locator(strategy.anchor)
                anchors = await self._visible_handles(anchor)
                count = len(anchors)
                for handle in anchors:
                    await handle.dispose()
                if count != 1:
                    return MatchSet(ambiguous_scope=count > 1)
                # Browser evaluates anchor and descendants in one locator query. Recheck
                # the anchor count afterward to reject a scope that became ambiguous.
                locator = anchor.get_by_role(strategy.role, name=strategy.name, exact=True)
            else:
                locator = self._locator(strategy)
            handles = await self._visible_handles(locator)
            if anchor is not None:
                anchors = await self._visible_handles(anchor)
                stable = len(anchors) == 1
                for handle in anchors:
                    await handle.dispose()
                if not stable:
                    for handle in handles:
                        await handle.dispose()
                    return MatchSet(ambiguous_scope=True)
            refs = []
            for handle in handles:
                token = uuid4().hex
                self._handles[token] = handle
                refs.append(TargetRef(token=token))
            return MatchSet(targets=refs)

    def _handle(self, target):
        try:
            return self._handles[target.token]
        except KeyError:
            raise SurfaceError("Unknown or expired target") from None

    async def observe(self, target: TargetRef | None = None) -> Observation:
        async with _translate_errors():
            if target is None:
                return await self._normalized_observation()
            handle = self._handle(target)
            return Observation(visible=await handle.is_visible(), text=await handle.inner_text())

    async def _normalized_observation(self) -> Observation:
        candidates = await self._page.locator(
            'input:not([type="hidden"]):not([type="password"]), button, select, textarea, a[href], [role="status"], [role="alert"]'
        ).element_handles()
        elements = []
        for handle in candidates[:80]:
            try:
                if not await handle.is_visible():
                    continue
                data = await handle.evaluate('''el => {
                    const kind = el.tagName.toLowerCase();
                    const label = [...(el.labels || [])].map(x => x.innerText).join(' ').trim();
                    const labelled = (el.getAttribute('aria-labelledby') || '').split(' ').map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
                    const text = (el.innerText || '').trim().slice(0, 200);
                    const role = el.getAttribute('role') || ({button:'button', input:'textbox', textarea:'textbox', select:'combobox', a:'link'}[kind] || 'generic');
                    const name = (el.getAttribute('aria-label') || labelled || label || (kind === 'input' ? '' : text)).slice(0, 200);
                    return {kind, label, text, role, name, enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
                            value: ['input','textarea','select'].includes(kind) ? el.value.slice(0, 200) : null,
                            htmlId: el.id, fieldName: el.getAttribute('name')};
                }''')
                strategies = []
                if data['name']:
                    strategies.append({'type': 'accessibility', 'role': data['role'], 'name': data['name']})
                if data['label']:
                    strategies.append({'type': 'label', 'value': data['label']})
                if data['text'] and data['kind'] not in {'input', 'select', 'textarea'}:
                    strategies.append({'type': 'text', 'value': data['text']})
                # CSS fallback uses only an escaped DOM identifier, never an nth-element shortcut.
                if data['htmlId']:
                    escaped = await handle.evaluate('el => CSS.escape(el.id)')
                    strategies.append({'type': 'css', 'value': f'#{escaped}'})
                if not strategies:
                    continue
                index = len(elements)
                target = SemanticTarget.model_validate({'concept': f'observed_{index}', 'strategies': strategies})
                elements.append(ObservedElement(id=f'e{index}', role=data['role'], name=data['name'],
                    label=data['label'], text=data['text'], kind=data['kind'], enabled=data['enabled'],
                    value=data['value'], target=target))
            finally:
                await handle.dispose()
        for handle in candidates[80:]:
            await handle.dispose()
        dialogs = await self._page.locator('dialog[open], [role="dialog"]:visible').all_inner_texts()
        frames = []
        for frame in await self._page.locator('iframe').element_handles():
            try:
                if len(frames) < 5:
                    frames.append(FrameInfo(title=(await frame.get_attribute('title')) or '',
                                            path=urlsplit((await frame.get_attribute('src')) or '').path))
            finally:
                await frame.dispose()
        body = await self._page.locator('body').inner_text()
        return Observation(visible=True, url=urlsplit(self._page.url).path,
                           title=(await self._page.title())[:200], text=body[:4000],
                           elements=elements, dialogs=[text[:300] for text in dialogs[:5]], frames=frames[:5])

    async def select(self, target: TargetRef, value: str, timeout_ms: int) -> None:
        async with _translate_errors():
            await self._handle(target).select_option(value=value, timeout=timeout_ms)

    async def click(self, target: TargetRef, timeout_ms: int) -> None:
        async with _translate_errors():
            await self._handle(target).click(timeout=timeout_ms)

    async def fill(self, target: TargetRef, value: str, timeout_ms: int) -> None:
        async with _translate_errors():
            await self._handle(target).fill(value, timeout=timeout_ms)

    async def extract(self, target: TargetRef, timeout_ms: int) -> str:
        async with _translate_errors():
            try:
                async with asyncio.timeout(timeout_ms / 1000):
                    return (await self._handle(target).inner_text()).strip()
            except TimeoutError:
                raise SurfaceTimeout("Extraction timed out") from None

    async def wait(self, target: TargetRef, expected: Expectation, timeout_ms: int) -> bool:
        deadline = monotonic() + timeout_ms / 1000
        while True:
            observation = await self.observe(target)
            if expected.kind == "absent" and not observation.visible:
                return True
            if expected.kind != "absent" and observation.visible:
                if expected.kind == "visible" or observation.text == expected.value:
                    return True
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(0.05, remaining))

    async def screenshot(self, path: Path) -> None:
        async with _translate_errors():
            # Conservative default: suppress every UI value, including financial data,
            # images, canvas, frames and CSS-generated text. No raw image is written.
            await self._page.screenshot(
                path=str(path), full_page=False,
                mask=[self._page.locator("html")], mask_color="#000000",
                style="*, *::before, *::after { visibility: hidden !important; } html { background: #000 !important; }",
            )

    async def release_targets(self) -> None:
        handles, self._handles = self._handles, {}
        for handle in handles.values():
            try:
                await handle.dispose()
            except Error:
                pass
