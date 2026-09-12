"""Small loopback control panel; operates on the manager's retained Surface."""
import asyncio
import json
from uuid import uuid4

from deterministic_ui.handoff import HandoffManager
from deterministic_ui.surface import SurfaceError


PAGE = r"""<!doctype html><meta charset="utf-8"><title>Same-session operator control</title>
<style>body{font:16px system-ui;max-width:950px;margin:30px auto}button{padding:12px;margin:5px}
pre{white-space:pre-wrap;background:#eee;padding:18px}#message{color:#833}</style>
<h1>Bank simulator operator control</h1>
<p>This panel controls the existing application session. Inspect the live state before acting.
Only the listed actions are supported and audited. No action restarts the workflow.</p>
<h2 id="state">Connecting…</h2><p id="reason"></p><small id="session"></small>
<div><button id="take" onclick="send('take')">Take control</button>
<button id="back" onclick="send('handback')">Hand back to automation</button>
<button id="cancel" onclick="send('cancel')">Stop run</button></div>
<div id="actions"></div><p id="message"></p><h2>Live application state</h2><pre id="page"></pre>
<script>
const base=location.pathname.replace(/\/$/,'');
async function send(command,id){
  const r=await fetch(base,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({command,id})});
  document.querySelector('#message').textContent=(await r.json()).status; await refresh();
}
async function refresh(){
 try{
  const r=await fetch(base+'/status'); const s=await r.json();
  document.querySelector('#state').textContent=s.state+' — '+s.owner;
  document.querySelector('#reason').textContent='Step: '+(s.step||'running')+' | Reason: '+(s.reason||'none');
  document.querySelector('#session').textContent='Retained session: '+s.session_id;
  document.querySelector('#page').textContent=s.page_text;
  document.querySelector('#take').disabled=!['PAUSED','HUMAN_REQUIRED'].includes(s.state);
  document.querySelector('#back').disabled=s.state!=='HUMAN_CONTROL';
  document.querySelector('#actions').replaceChildren(...s.actions.map(a=>{
   const b=document.createElement('button');b.textContent=a.label;b.disabled=s.state!=='HUMAN_CONTROL';
   b.onclick=()=>send('action',a.id);return b;
  }));
 }catch(e){document.querySelector('#message').textContent='Session closed or unavailable';}
}
refresh();setInterval(refresh,1000);
</script>"""


class OperatorServer:
    def __init__(self, manager: HandoffManager):
        self.manager = manager
        self.token = uuid4().hex
        self.server = None
        self.url = ""

    async def __aenter__(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        port = self.server.sockets[0].getsockname()[1]
        self.origin = f"http://127.0.0.1:{port}"
        self.url = f"{self.origin}/{self.token}"
        return self

    async def __aexit__(self, *_):
        assert self.server is not None
        self.server.close()
        await self.server.wait_closed()

    async def _handle(self, reader, writer):
        code, content_type = 200, "application/json"
        try:
            async with asyncio.timeout(10):
                header = await reader.readuntil(b"\r\n\r\n")
                lines = header.decode("ascii").split("\r\n")
                method, path, _ = lines[0].split()
                headers = dict(line.split(": ", 1) for line in lines[1:] if line)
                headers = {key.lower(): value for key, value in headers.items()}
                if headers.get("host") != self.origin.removeprefix("http://"):
                    raise ValueError
                if headers.get("origin", self.origin) != self.origin:
                    raise ValueError
                if method == "GET" and path == f"/{self.token}":
                    content_type, body = "text/html; charset=utf-8", PAGE.encode()
                elif method == "GET" and path == f"/{self.token}/status":
                    body = json.dumps(await self.manager.status()).encode()
                elif method == "POST" and path == f"/{self.token}":
                    length = int(headers.get("content-length", "0"))
                    if not 0 < length <= 4096:
                        raise ValueError
                    request = json.loads(await reader.readexactly(length))
                    command = request["command"]
                    if command == "take":
                        await self.manager.take_control()
                    elif command == "handback":
                        await self.manager.handback()
                    elif command == "action":
                        await self.manager.human_action(request["id"])
                    elif command == "cancel":
                        await self.manager.cancel()
                    else:
                        raise ValueError
                    body = b'{"status":"Request handled; inspect current state"}'
                else:
                    code, body = 404, b'{"status":"Not found"}'
        except SurfaceError:
            code, body = 409, b'{"status":"Control or action rejected; inspect current state"}'
        except Exception:
            code, body = 400, b'{"status":"Request rejected"}'
        writer.write((f"HTTP/1.1 {code} Response\r\nContent-Type: {content_type}\r\n"
                      f"Content-Length: {len(body)}\r\nCache-Control: no-store\r\n"
                      "X-Frame-Options: DENY\r\nConnection: close\r\n\r\n").encode() + body)
        try:
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
