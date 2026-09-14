import os

import pytest

from acceptance.discovery_handoff import exercise
from deterministic_ui.playwright_surface import PlaywrightSurface

pytestmark=pytest.mark.skipif(os.environ.get('RUN_BROWSER_TESTS')!='1',reason='Set RUN_BROWSER_TESTS=1')


async def test_discovery_same_page_handoff(tmp_path,monkeypatch):
    pages=[]
    original=PlaywrightSurface.observe
    async def observe(self,target=None):
        pages.append((id(self._page),id(self._page.context)))
        return await original(self,target)
    monkeypatch.setattr(PlaywrightSurface,'observe',observe)
    result=await exercise(tmp_path)
    assert result['status']=='PASS' and result['provider']=='mock'
    assert len(set(pages))==1
