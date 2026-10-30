"""
🌐 Hashbrown Chat website: lets friends use the chat from a browser instead of client.py.

Run:   python web/web_server.py          (next to a running server.py)
Then:  open the "Share this link" address it prints, on any phone or computer on the same Wi-Fi.

It serves the page in web/static/ and works as a bridge: every browser tab gets its own
connection to the chat server on port 8820 (see bridge.py).
  POST /api/session            -> a new session id
  POST /api/send               -> one message to the chat server  (header X-Session-Id)
  GET  /api/events?sid=&last=  -> Server-Sent Events, one per message from the chat server
  POST /api/close              -> log out
"""
import argparse
import ipaddress
import json
import os
import signal
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from bridge import BridgeError, Registry

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BODY = 4 * 1024 * 1024
SMALL_BODY = 1024        # /api/session and /api/close carry an empty JSON object
BODY_DEADLINE = 60       # seconds to upload a whole body (a 4 MB file on slow Wi-Fi)
MAX_CONNECTIONS = 200    # open HTTP connections at once; more are dropped
KEEPALIVE = 15           # seconds between SSE heartbeats
STATIC_TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript",
                ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}
SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'none'; script-src 'self'; style-src 'self'; "
                                "img-src 'self' data: blob:; connect-src 'self'; manifest-src 'self'; "
                                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def log(text):
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode(), flush=True)


def load_static():
    """URL path -> (file path, content type), built once. Requests are only ever looked up
    in this table, so no part of a URL ever reaches the file system."""
    files = {}
    for folder, _, names in os.walk(STATIC_DIR):
        for name in names:
            path = os.path.join(folder, name)
            kind = STATIC_TYPES.get(os.path.splitext(name)[1])
            if kind is None or os.path.islink(path):
                continue
            url = "/" + os.path.relpath(path, STATIC_DIR).replace(os.sep, "/")
            files[url] = (path, kind + ("; charset=utf-8" if kind.startswith("text/") else ""))
    if "/index.html" in files:
        files["/"] = files["/index.html"]
    return files


def lan_ip():
    """This computer's address on the Wi-Fi. Connecting a UDP socket sends nothing,
    it just makes the OS pick the network interface it would use."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.254.254.254", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


class Handler(BaseHTTPRequestHandler):
    server_version = "Hashbrown"
    sys_version = ""
    timeout = 20  # seconds for any single read or write, so stuck connections get dropped

    # ----- logging: never message contents, passwords or session ids (they're in the URL)

    def setup(self):
        super().setup()
        # Notice phones that vanish without closing the connection, so their session can expire
        self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for name, value in (("TCP_KEEPIDLE", 30), ("TCP_KEEPALIVE", 30), ("TCP_KEEPINTVL", 10), ("TCP_KEEPCNT", 3)):
            if hasattr(socket, name):
                self.connection.setsockopt(socket.IPPROTO_TCP, getattr(socket, name), value)

    def log_request(self, code="-", size="-"):
        if isinstance(code, int) and code >= 400:
            path = ascii(urlsplit(self.path or "").path[:80])  # ascii(): no terminal escape codes from strangers
            log(f"[WEB] {self.client_address[0]} {ascii(self.command or '-')} {path} -> {code}")

    def log_error(self, *args):
        pass  # send_error() already goes through log_request

    # ----- responses

    def send_headers(self, status, content_type, length=None, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        for name, value in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(name, value)
        self.end_headers()

    def reply(self, status, **fields):
        body = json.dumps({"ok": status < 400, **fields}, ensure_ascii=False).encode()
        self.send_headers(status, "application/json; charset=utf-8", len(body), {"Cache-Control": "no-store"})
        self.wfile.write(body)

    def fail(self, status, text):
        self.close_connection = True
        self.reply(status, error=text)

    # ----- guards

    def host_ok(self):
        """Only answer to an IP address, localhost or a name given with --allow-host.
        This stops DNS rebinding: a web page on evil.example can't reach us by name."""
        host = urlsplit("//" + self.headers.get("Host", "")).hostname or ""
        if host in self.server.allowed_hosts:
            return True
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False

    def same_origin(self):
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            return False
        return self.headers.get("Sec-Fetch-Site", "same-origin") in ("same-origin", "none")

    def read_json(self, limit=MAX_BODY):
        if self.headers.get("X-Hashbrown") != "1" or not self.same_origin():
            raise BridgeError(403, "Requests must come from the Hashbrown page.")
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise BridgeError(415, "Send JSON.")
        length = self.headers.get("Content-Length", "")
        if not length.isdecimal():
            raise BridgeError(411, "Content-Length is required.")
        if int(length) > limit:
            raise BridgeError(413, "That's too big (4 MB max).")
        raw = self.read_body(int(length))
        try:
            return json.loads(raw.decode("utf-8"), parse_constant=self._no_constants)
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise BridgeError(400, "That wasn't valid JSON.") from None

    def read_body(self, length):
        """Read the body with a deadline for the whole thing, not just for each piece."""
        deadline = time.monotonic() + BODY_DEADLINE
        chunks, left = [], length
        while left:
            if time.monotonic() > deadline:
                raise BridgeError(408, "The upload took too long.")
            chunk = self.rfile.read1(min(left, 65536))
            if not chunk:
                raise BridgeError(400, "The upload was cut off.")
            chunks.append(chunk)
            left -= len(chunk)
        return b"".join(chunks)

    @staticmethod
    def _no_constants(name):
        raise ValueError(f"{name} is not allowed")

    def session(self, sid):
        return self.server.registry.get(sid, self.client_address[0])

    # ----- routing

    def do_GET(self):
        if not self.host_ok():
            return self.fail(421, "Unknown host.")
        url = urlsplit(self.path)
        if url.path == "/api/events":
            return self.guarded(lambda: self.events(parse_qs(url.query)))
        if url.path.startswith("/api/"):
            return self.fail(404, "Not found.")
        found = self.server.static.get(url.path)
        if found is None:
            return self.fail(404, "Not found.")
        path, kind = found
        with open(path, "rb") as f:
            body = f.read()
        self.send_headers(200, kind, len(body), {"Cache-Control": "no-cache"})
        self.wfile.write(body)

    def do_POST(self):
        if not self.host_ok():
            return self.fail(421, "Unknown host.")
        routes = {"/api/session": self.new_session, "/api/send": self.send_message, "/api/close": self.close}
        route = routes.get(urlsplit(self.path).path)
        if route is None:
            return self.fail(404, "Not found.")
        self.guarded(route)

    def guarded(self, action):
        try:
            action()
        except BridgeError as e:
            self.fail(e.status, e.text)

    def new_session(self):
        self.read_json(SMALL_BODY)
        session = self.server.registry.create(self.client_address[0])
        self.reply(200, sid=session.sid)

    def send_message(self):
        session = self.session(self.headers.get("X-Session-Id"))
        msg = self.read_json()
        if isinstance(msg, dict) and msg.get("type") == "auth":
            self.server.registry.check_login_allowed(session.ip)
        session.forward(msg)
        self.reply(202)

    def close(self):
        session = self.session(self.headers.get("X-Session-Id"))
        self.read_json(SMALL_BODY)
        self.server.registry.close(session)
        self.reply(200)

    # ----- Server-Sent Events

    def events(self, query):
        if not self.same_origin():
            raise BridgeError(403, "Requests must come from the Hashbrown page.")
        session = self.session(query.get("sid", [""])[0])
        resume = (self.headers.get("Last-Event-ID") or query.get("last", ["0"])[0])[:18]
        last = int(resume) if resume.isdecimal() else 0
        generation = session.attach()
        self.close_connection = True
        try:
            self.send_headers(200, "text/event-stream; charset=utf-8",
                              extra={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
            self.write_sse("retry: 2000\n\n")
            last = self.stream(session, generation, last)
        except OSError:
            pass  # the tab went away
        finally:
            session.detach(generation)

    def stream(self, session, generation, last):
        live_sent = False
        while True:
            with session.cond:
                session.cond.wait_for(lambda: session.last_id > last or session.dead
                                      or session.stream != generation or not live_sent, timeout=KEEPALIVE)
                missed, gap = session.since(last)
                replaced, dead = session.stream != generation, session.dead
            if gap:
                self.write_bridge("gap")
            chunk = "".join(f"id: {event_id}\ndata: {text}\n\n" for event_id, text in missed)
            if missed:
                last = missed[-1][0]
            if chunk or not live_sent:
                self.write_sse(chunk)
                with session.cond:
                    session.forget_sent(last)   # 📦 live-only events (big file chunks) are delivered: done
            if not live_sent:  # everything before this was replay, everything after is live
                self.write_bridge("live", logged_in=session.logged_in)
                live_sent = True
            elif not chunk and not replaced and not dead:
                self.write_sse(": keepalive\n\n")
            if replaced:
                self.write_bridge("replaced")
                return last
            if dead and session.last_id <= last:
                self.write_bridge("closed", reason=dead)
                return last

    def write_bridge(self, event, **fields):
        self.write_sse(f"event: bridge\ndata: {json.dumps({'event': event, **fields}, ensure_ascii=False)}\n\n")

    def write_sse(self, text):
        if text:
            self.wfile.write(text.encode("utf-8"))
            self.wfile.flush()


class Server(ThreadingHTTPServer):
    """Threads per connection, but never more than MAX_CONNECTIONS at once."""
    daemon_threads = True
    slots = threading.BoundedSemaphore(MAX_CONNECTIONS)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def main():
    parser = argparse.ArgumentParser(description="Hashbrown Chat website")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--chat-host", default="127.0.0.1")
    parser.add_argument("--chat-port", type=int, default=8820)
    parser.add_argument("--max-sessions", type=int, default=50)
    parser.add_argument("--allow-host", action="append", default=[],
                        help="a host name the site may be opened with, besides IP addresses")
    args = parser.parse_args()

    server = Server(("0.0.0.0", args.port), Handler)
    server.registry = Registry((args.chat_host, args.chat_port), args.max_sessions)
    server.static = load_static()
    server.allowed_hosts = {"localhost", *args.allow_host}
    if "/" not in server.static:
        log(f"[WEB] ❌ Can't find {os.path.join(STATIC_DIR, 'index.html')}")
        return

    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)

    ip = lan_ip()
    log(f"[WEB] 🌐 Hashbrown website running on port {args.port} (Ctrl+C to stop)")
    log(f"[WEB] 🔗 Share this link: http://{ip}:{args.port}")
    if ip == "127.0.0.1":
        log("[WEB] ⚠️ No Wi-Fi network found, so only this computer can open the site.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        log("\n[WEB] Shutting down.")
        server.registry.close_all()
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
