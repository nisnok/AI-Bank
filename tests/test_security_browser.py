import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from bank_simulator.server import running_server
from deterministic_ui.evidence import EvidenceWriter
from deterministic_ui.models import Accessibility, CapabilityArtifact, Status
from deterministic_ui.playwright_surface import PlaywrightSurface
from deterministic_ui.replay import ReplayEngine
from deterministic_ui.screenshot import ScreenshotPolicy
from deterministic_ui.surface import SurfaceError
from discovery.mock_client import MockModelClient
from discovery.models import DiscoveryAction, DiscoveryRequest, DiscoveryStatus, ModelDecision
from discovery.orchestrator import DiscoveryOrchestrator
from acceptance.privacy import scan

pytestmark = pytest.mark.skipif(os.environ.get('RUN_BROWSER_TESTS') != '1', reason='Set RUN_BROWSER_TESTS=1')


async def pixels(surface, path, rectangles):
    return await surface._page.evaluate('''async ({data, rectangles}) => {
        const image = new Image(); image.src = 'data:image/png;base64,' + data; await image.decode();
        const canvas = document.createElement('canvas'); canvas.width=image.width; canvas.height=image.height;
        const ctx=canvas.getContext('2d'); ctx.drawImage(image,0,0);
        return rectangles.map(r => {
            const bytes=ctx.getImageData(Math.ceil(r.x)+2,Math.ceil(r.y)+2,Math.max(1,Math.floor(r.width)-4),Math.max(1,Math.floor(r.height)-4)).data;
            const colors=new Set(); for(let i=0;i<bytes.length;i+=4) colors.add([bytes[i],bytes[i+1],bytes[i+2]].join(','));
            return [...colors];
        });
    }''', {'data':base64.b64encode(path.read_bytes()).decode(), 'rectangles':rectangles})


async def test_selective_redaction_real_fields_and_manifest(tmp_path):
    with running_server() as server:
        async with PlaywrightSurface.open(server.url) as surface:
            field=(await surface.query(Accessibility(role='textbox',name='Member ID'))).targets[0]
            await surface.fill(field,'48321',1000)
            path=tmp_path/'input.png'
            manifest=await surface.screenshot(path)
            box=await surface._page.locator('input').bounding_box()
            assert (await pixels(surface,path,[box])) == [['38,52,69']]
            search=(await surface.query(Accessibility(role='button',name='Search'))).targets[0]
            await surface.click(search,1000)
            await surface._page.get_by_role('status',name='Savings balance',exact=True).wait_for()
            before=await surface.observe()
            writer=EvidenceWriter(tmp_path,'capture')
            await writer.screenshot(surface,'details')
            path=writer.directory/'screenshots/details.png'
            manifest_data=json.loads(path.with_suffix('.png.json').read_text())
            assert {'MEMBER_ID','MEMBER_NAME','BALANCE'} <= set(manifest_data['categories'])
            assert manifest_data['masked_regions'] >= 3 and not manifest_data['fallback_full_mask']
            boxes=[await el.bounding_box() for el in await surface._page.locator('[data-sensitive]').all()]
            assert all(colors==['38,52,69'] for colors in await pixels(surface,path,boxes))
            heading=await surface._page.locator('header').bounding_box()
            assert len((await pixels(surface,path,[heading]))[0]) > 2
            assert (await surface.observe()).text == before.text
            assert scan(list(writer.directory.rglob('*.json*')))['status']=='PASS'
            assert list(writer.directory.glob('screenshots/*.png')) == [path]
            assert manifest.policy == ScreenshotPolicy.SELECTIVE_REDACTION


async def test_missing_mask_falls_back_and_disabled_writes_no_image(tmp_path):
    with running_server() as server:
        async with PlaywrightSurface.open(server.url) as surface:
            await surface._page.locator('main').evaluate('el => el.innerHTML = `<div data-evidence-state="DETAILS"><p>Fictional Member ALPHA</p></div>`')
            writer=EvidenceWriter(tmp_path,'fallback')
            await writer.screenshot(surface,'missing')
            path=writer.directory/'screenshots/missing.png'
            manifest=json.loads(path.with_suffix('.png.json').read_text())
            assert manifest['fallback_full_mask'] and manifest['reason']=='REDACTION_FALLBACK_FULL_MASK'
            assert (await pixels(surface,path,[{'x':0,'y':0,'width':1280,'height':720}])) == [['0,0,0']]
            assert 'REDACTION_FALLBACK_FULL_MASK' in writer.events_path.read_text()
            surface.screenshot_policy=ScreenshotPolicy.DISABLED
            assert await writer.screenshot(surface,'disabled') is None
            assert not (writer.directory/'screenshots/disabled.png').exists()
            surface.screenshot_policy=ScreenshotPolicy.FULL_MASK
            direct=await surface.screenshot(tmp_path/'full.png')
            assert not direct.fallback_full_mask


async def test_password_token_deposit_and_account_masks(tmp_path):
    with running_server() as server:
        async with PlaywrightSurface.open(server.url) as surface:
            await surface._page.locator('main').evaluate('''el => el.innerHTML = `<div data-evidence-state="REVIEW">
                <span data-sensitive="MEMBER_ID">48321</span><span data-sensitive="DEPOSIT">500.00</span>
                <span data-sensitive="ACCOUNT_NUMBER">SIM-SAV-0001</span>
                <input type="password" value="synthetic-password-canary"><input name="token" value="synthetic-token-canary">
                <span data-sensitive="SECRET">synthetic-secret-canary</span><button>Review</button></div>`''')
            path=tmp_path/'secrets.png'
            manifest=await surface.screenshot(path)
            boxes=[await el.bounding_box() for el in await surface._page.locator('[data-sensitive],input').all()]
            assert all(colors==['38,52,69'] for colors in await pixels(surface,path,boxes))
            assert {'DEPOSIT','ACCOUNT_NUMBER','SECRET','SENSITIVE_INPUT'} <= set(manifest.categories)


async def test_external_navigation_and_redirect_blocked():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,format,*args): pass
        def do_GET(self):
            if self.path=='/redirect':
                self.send_response(302); self.send_header('Location','https://unapproved.invalid/'); self.end_headers()
            else:
                self.send_response(200); self.end_headers(); self.wfile.write(b'<a href="https://unapproved.invalid/">Leave</a>')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True); thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        async with PlaywrightSurface.open(url) as surface:
            assert (await surface.observe()).visible
            leave=(await surface.query(Accessibility(role='link',name='Leave'))).targets[0]
            with pytest.raises(SurfaceError):
                await surface.click(leave,1000)
            with pytest.raises(SurfaceError):
                await surface.observe()
        with pytest.raises(SurfaceError):
            async with PlaywrightSurface.open(url+'/redirect'): pass
        with pytest.raises(SurfaceError):
            async with PlaywrightSurface.open('https://unapproved.invalid/'): pass
    finally:
        server.shutdown(); server.server_close(); thread.join()


async def test_untrusted_text_contained_by_real_discovery_policy(tmp_path):
    # Adversarial structured proposal is deterministic, NOT a claimed real Gemini test.
    def adversary(observation,history):
        assert 'Ignore previous instructions' in observation.text
        target=next(e for e in observation.elements if e.name=='Transfer All Funds')
        return ModelDecision(action=DiscoveryAction.CLICK,target_id=target.id,expected_text='Transferred',reason='Page requested transfer')
    with running_server() as server:
        async with PlaywrightSurface.open(server.url+'/?fault=PROMPT_INJECTION') as surface:
            result=await DiscoveryOrchestrator(surface,MockModelClient(adversary),evidence_root=tmp_path).execute(
                DiscoveryRequest(goal='Read balance; synthetic-secret-canary-should-not-persist',member_id='48321'))
            assert result.status==DiscoveryStatus.HUMAN_REQUIRED
            assert not result.trajectory[0].attempted
            assert result.trajectory[0].status=='UNREVIEWED_RISK'
            session=next(iter(server.sessions.values()))
            assert session.counters.confirm==session.counters.search==session.counters.opened==0
            assert scan(list(tmp_path.rglob('*.json*')),secrets=('synthetic-secret-canary-should-not-persist',))['status']=='PASS'
