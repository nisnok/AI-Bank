"""Only this module may import or retain Playwright objects."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic
from uuid import uuid4

from playwright.async_api import ElementHandle, Error, Locator, Page, TimeoutError as BrowserTimeout, async_playwright

from .models import Anchor, Expectation, FrameInfo, MatchSet, Observation, ObservedElement, SemanticTarget, Strategy, TargetRef
from .origins import OriginPolicy
from .screenshot import ScreenshotManifest, ScreenshotPolicy
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

    def __init__(self, page: Page, origins: OriginPolicy | None = None,
                 screenshot_policy: ScreenshotPolicy = ScreenshotPolicy.SELECTIVE_REDACTION):
        # Internal use only; public callers use open(), which yields a Surface.
        self._page = page
        self._origins = origins or OriginPolicy.for_url(page.url)
        self._origin_blocked = False
        self.screenshot_policy = screenshot_policy
        self._handles: dict[str, ElementHandle] = {}

    @classmethod
    @asynccontextmanager
    async def open(cls, url: str, *, headless: bool = True,
                   allowed_origins: frozenset[str] | None = None,
                   screenshot_policy: ScreenshotPolicy = ScreenshotPolicy.SELECTIVE_REDACTION):
        origins = OriginPolicy.for_url(url, allowed_origins)
        async with _translate_errors():
            async with async_playwright() as provider:
                browser = await provider.chromium.launch(headless=headless)
                try:
                    context = await browser.new_context(service_workers="block", accept_downloads=False)
                    page = await context.new_page()
                    surface = cls(page, origins, screenshot_policy)

                    async def guard(route):
                        # Context-wide routing covers frames, popups, redirects and fetch.
                        if not origins.permits(route.request.url):
                            surface._origin_blocked = True
                            await route.abort("blockedbyclient")
                        else:
                            await route.continue_()

                    await context.route("**/*", guard)
                    # WebSockets are not part of the Surface contract.
                    await context.route_web_socket("**/*", lambda socket: socket.close())
                    await page.goto(url, wait_until="domcontentloaded")
                    surface._check_origin()
                    yield surface
                finally:
                    await browser.close()

    def _check_origin(self):
        if self._origin_blocked or not self._origins.permits(self._page.url):
            raise SurfaceError("ORIGIN_NOT_ALLOWED")

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
        self._check_origin()
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
        self._check_origin()
        async with _translate_errors():
            if target is None:
                return await self._normalized_observation()
            handle = self._handle(target)
            value = await handle.evaluate("el => ['INPUT','SELECT','TEXTAREA'].includes(el.tagName) ? el.value : null")
            return Observation(visible=await handle.is_visible(), text=await handle.inner_text(), value=value)

    async def _normalized_observation(self) -> Observation:
        # One synchronous DOM evaluation prevents mixed snapshots when a response
        # replaces the page between element collection and visible-text collection.
        snapshot = await self._page.evaluate("""() => {
            const visible = el => {
                const style = getComputedStyle(el);
                return style.visibility !== 'hidden' && style.visibility !== 'collapse'
                    && !!(el.getBoundingClientRect().width && el.getBoundingClientRect().height);
            };
            const elements = [...document.querySelectorAll(
                'input:not([type="hidden"]):not([type="password"]), button, select, textarea, a[href], [role="status"], [role="alert"]'
            )].slice(0, 80).filter(visible).map(el => {
                const kind = el.tagName.toLowerCase();
                const label = [...(el.labels || [])].map(x => x.innerText).join(' ').trim();
                const labelled = (el.getAttribute('aria-labelledby') || '').split(' ').map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
                const text = (el.innerText || '').trim().slice(0, 200);
                const role = el.getAttribute('role') || ({button:'button', input:'textbox', textarea:'textbox', select:'combobox', a:'link'}[kind] || 'generic');
                const name = (el.getAttribute('aria-label') || labelled || label || (kind === 'input' ? '' : text)).slice(0, 200);
                return {kind, label, text, role, name, enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
                        value: ['input','textarea','select'].includes(kind) ? el.value.slice(0, 200) : null,
                        css: el.id ? '#' + CSS.escape(el.id) : null};
            });
            return {elements, title: document.title.slice(0, 200), path: location.pathname,
                    text: (document.body?.innerText || '').slice(0, 4000),
                    dialogs: [...document.querySelectorAll('dialog[open], [role="dialog"]')].filter(visible).slice(0, 5).map(el => el.innerText.slice(0, 300)),
                    frames: [...document.querySelectorAll('iframe')].slice(0, 5).map(el => ({title: el.title, path: new URL(el.src || '/', location.href).pathname}))};
        }""")
        elements = []
        for data in snapshot['elements']:
            strategies = []
            if data['name']:
                strategies.append({'type':'accessibility', 'role':data['role'], 'name':data['name']})
            if data['label']:
                strategies.append({'type':'label', 'value':data['label']})
            if data['text'] and data['kind'] not in {'input','select','textarea'}:
                strategies.append({'type':'text', 'value':data['text']})
            if data['css']:
                strategies.append({'type':'css', 'value':data['css']})
            if not strategies:
                continue
            index = len(elements)
            target = SemanticTarget.model_validate({'concept':f'observed_{index}', 'strategies':strategies})
            elements.append(ObservedElement(id=f'e{index}', role=data['role'], name=data['name'],
                label=data['label'], text=data['text'], kind=data['kind'], enabled=data['enabled'],
                value=data['value'], target=target))
        return Observation(visible=True, url=snapshot['path'], title=snapshot['title'], text=snapshot['text'],
                           elements=elements, dialogs=snapshot['dialogs'],
                           frames=[FrameInfo.model_validate(frame) for frame in snapshot['frames']])

    async def select(self, target: TargetRef, value: str, timeout_ms: int) -> None:
        self._check_origin()
        async with _translate_errors():
            await self._handle(target).select_option(value=value, timeout=timeout_ms)

    async def click(self, target: TargetRef, timeout_ms: int) -> None:
        self._check_origin()
        async with _translate_errors():
            await self._handle(target).click(timeout=timeout_ms)
            self._check_origin()

    async def fill(self, target: TargetRef, value: str, timeout_ms: int) -> None:
        self._check_origin()
        async with _translate_errors():
            await self._handle(target).fill(value, timeout=timeout_ms)

    async def extract(self, target: TargetRef, timeout_ms: int) -> str:
        self._check_origin()
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
                actual = observation.value if expected.kind == "value_equals" else observation.text
                if expected.kind == "visible" or actual == expected.value:
                    return True
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(0.05, remaining))

    async def screenshot(self, path: Path) -> ScreenshotManifest:
        self._check_origin()
        policy = self.screenshot_policy
        if policy == ScreenshotPolicy.DISABLED:
            return ScreenshotManifest(policy=policy)
        async with _translate_errors():
            if policy == ScreenshotPolicy.SELECTIVE_REDACTION:
                before = await self._redaction_inventory()
                if before["valid"]:
                    # Masks and stylesheet are applied by Chromium before encoding. No
                    # unmasked path is ever passed to screenshot(). Broad cell/input masks
                    # also cover newly inserted values during normal simulator transitions.
                    selector = '[data-sensitive], input, textarea, select, [contenteditable], td, iframe, canvas, img, video'
                    safe = await self._page.screenshot(full_page=False,
                        mask=[self._page.locator(selector)], mask_color="#263445",
                        animations="disabled", caret="hide",
                        style=selector + ' { color: transparent !important; text-shadow: none !important; }')
                    after = await self._redaction_inventory()
                    if after == before:
                        path.write_bytes(safe)
                        return ScreenshotManifest(policy=policy, masked_regions=before["count"],
                                                  categories=before["categories"])
                # Unknown profile, missing required category, or a changed DOM: discard
                # the in-memory image and capture a full mask. Never persist raw pixels.
            safe = await self._page.screenshot(full_page=False,
                mask=[self._page.locator("html")], mask_color="#000000",
                style="*, *::before, *::after { visibility: hidden !important; } html { background: #000 !important; }")
            path.write_bytes(safe)
            fallback = policy == ScreenshotPolicy.SELECTIVE_REDACTION
            return ScreenshotManifest(policy=policy, masked_regions=1, categories=["FULL_PAGE"],
                fallback_full_mask=fallback, reason="REDACTION_FALLBACK_FULL_MASK" if fallback else None)

    async def _redaction_inventory(self):
        return await self._page.evaluate("""() => {
            const root = document.querySelector('main > [data-evidence-state]');
            const required = {
                SEARCH: [], DETAILS: ['MEMBER_ID', 'MEMBER_NAME', 'BALANCE'],
                OPENING: ['MEMBER_ID', 'DEPOSIT'], REVIEW: ['MEMBER_ID', 'DEPOSIT'],
                CONFIRMED: ['MEMBER_ID', 'DEPOSIT', 'ACCOUNT_NUMBER'],
                INVALID_DEPOSIT: ['MEMBER_ID', 'DEPOSIT'], LOADING: [], ERROR: [],
                MEMBER_NOT_FOUND: [], MEMBER_INELIGIBLE: [], SESSION_EXPIRED: [],
                PERMISSION_DENIED: [], INVALID_STATE: []
            };
            const known = ['MEMBER_ID','MEMBER_NAME','BALANCE','ACCOUNT_NUMBER','DEPOSIT','SECRET'];
            const nodes = [...document.querySelectorAll('[data-sensitive], input, textarea, select, [contenteditable], td, iframe, canvas, img, video')];
            const visible = nodes.filter(el => !!(el.getBoundingClientRect().width && el.getBoundingClientRect().height));
            const categories = [...new Set(visible.map(el => known.includes(el.dataset.sensitive) ? el.dataset.sensitive :
                ['INPUT','TEXTAREA','SELECT'].includes(el.tagName) || el.hasAttribute('contenteditable') ? 'SENSITIVE_INPUT' :
                el.tagName === 'TD' ? 'TABLE_VALUE' : 'EMBEDDED_CONTENT'))].sort();
            const state = root?.dataset.evidenceState;
            const valid = document.body?.dataset.evidenceProfile === 'simulator-v1' &&
                document.querySelectorAll('main > [data-evidence-state]').length === 1 &&
                Object.hasOwn(required, state || '') && required[state].every(cat => categories.includes(cat));
            // HTML used only in memory to detect changes around capture, never persisted.
            return {valid, count: visible.length, categories, state, revision: document.body?.innerHTML.replace(/ style=""/g, '')};
        }""")

    async def release_targets(self) -> None:
        handles, self._handles = self._handles, {}
        for handle in handles.values():
            try:
                await handle.dispose()
            except Error:
                pass
