"""Loopback-only threaded HTTP server; no database or external services."""
import argparse
from contextlib import contextmanager
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from time import sleep
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from .domain import Drift, Fault, Session, Tenant
from .views import REFERENCE, render_state, shell


class SimulatorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int = 8765, *, slow_ms: int = 10000):
        self.sessions: dict[str, Session] = {}
        self.lock = Lock()
        self.slow_ms = slow_ms
        super().__init__(("127.0.0.1", port), Handler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    @property
    def simulator(self) -> SimulatorServer:
        assert isinstance(self.server, SimulatorServer)
        return self.server

    def log_message(self, format: str, *args) -> None:
        # No request bodies, identifiers, or arbitrary URLs in server logs.
        pass

    def reply(self, html: str, status: int = 200, cookie: str | None = None) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if cookie:
            self.send_header("Set-Cookie", f"training_session={cookie}; HttpOnly; SameSite=Strict; Path=/")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # A timeout may close a browser while a delayed response is pending.

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path == "/reference":
            self.reply(REFERENCE)
            return
        if url.path != "/":
            self.reply("Not found", 404)
            return
        query = parse_qs(url.query)
        try:
            fault = Fault(query.get("fault", ["NONE"])[0])
            tenant = Tenant(query.get("tenant", ["bank_a"])[0])
            drift = Drift(query.get("drift", ["none"])[0])
            application_version = query.get("application_version", ["1"])[0]
            if application_version not in {"1", "2"}:
                raise ValueError
        except ValueError:
            self.reply("Unknown fault mode", 400)
            return
        session = Session(fault=fault, fallback=query.get("variant", [""])[0] == "fallback",
                          tenant=tenant, drift=drift, application_version=application_version)
        token = uuid4().hex
        with self.simulator.lock:
            self.simulator.sessions[token] = session
        self.reply(shell(session), cookie=token)

    def do_POST(self) -> None:
        if self.path not in {"/search", "/open", "/review", "/confirm"}:
            self.reply("Not found", 404)
            return
        origin = self.headers.get("Origin")
        if origin is not None and origin != self.simulator.url:
            self.reply("Origin denied", 403)
            return
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        token = cookie.get("training_session")
        with self.simulator.lock:
            session = self.simulator.sessions.get(token.value) if token else None
        if session is None:
            self.reply("Employee session expired", 401)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 4096:
                raise ValueError
            values = parse_qs(self.rfile.read(length).decode("utf-8"), max_num_fields=10)
        except (ValueError, UnicodeError):
            self.reply("Invalid form", 400)
            return
        with self.simulator.lock:
            if self.path == "/search":
                state = session.search(values.get("member_id", [""])[0])
            elif self.path == "/open":
                state = session.begin()
            elif self.path == "/review":
                state = session.review(values.get("initial_deposit", [""])[0])
            else:
                state = session.confirm()
            html = render_state(session, state)
        if self.path == "/search" and session.fault == Fault.SLOW_PAGE:
            sleep(self.simulator.slow_ms / 1000)  # Intentional, configured fault at the HTTP boundary.
        self.reply(html)


@contextmanager
def running_server(*, slow_ms: int = 10000):
    """Ephemeral local server for browser tests; no fixed-port collision or startup sleep."""
    server = SimulatorServer(0, slow_ms=slow_ms)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the local fictional banking simulator")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--slow-ms", type=int, default=10000)
    args = parser.parse_args()
    if args.slow_ms < 0:
        parser.error("--slow-ms must be nonnegative")
    server = SimulatorServer(args.port, slow_ms=args.slow_ms)
    print(f"Fictional banking simulator: {server.url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
