"""🧪 Test helpers: a pretend client.py and a pretend Foundry AI server."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TIMEOUT = 5  # seconds to wait for a message before a test fails


class FakeClient:
    """A pretend client.py: sends JSON lines and keeps everything the server sends back."""

    def __init__(self, port):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=TIMEOUT)
        self.sock.settimeout(None)
        self.messages = []   # every message received, in order
        self.seen = 0        # expect() looks at messages after this index
        self.closed = False  # True once the server hung up
        self.arrived = threading.Condition()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        buffer = b""
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    with self.arrived:
                        self.messages.append(json.loads(line.decode("utf-8")))
                        self.arrived.notify_all()
        except OSError:
            pass
        with self.arrived:
            self.closed = True
            self.arrived.notify_all()

    # --- sending
    def send_raw(self, data):
        self.sock.sendall(data)

    def send(self, obj):
        self.send_raw((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))

    def line(self, text):
        self.send({"type": "line", "text": text})

    # --- waiting for answers
    def expect(self, check, timeout=TIMEOUT):
        """The next message (after the last one expect() returned) where check(msg) is True."""
        deadline = time.monotonic() + timeout
        with self.arrived:
            while True:
                while self.seen < len(self.messages):
                    msg = self.messages[self.seen]
                    self.seen += 1
                    if check(msg):
                        return msg
                if self.closed:
                    raise AssertionError(f"server hung up. Last messages: {self.messages[-5:]}")
                left = deadline - time.monotonic()
                if left <= 0:
                    raise AssertionError(f"timed out. Last messages: {self.messages[-5:]}")
                self.arrived.wait(left)

    def expect_text(self, part, kind=None, timeout=TIMEOUT):
        return self.expect(lambda m: part in str(m.get("text", ""))
                           and (kind is None or m.get("kind") == kind), timeout)

    def expect_board(self, my_turn=None):
        return self.expect(lambda m: m.get("kind") == "board" and "state" in m
                           and (my_turn is None or m["state"].get("your_turn") == my_turn))

    def sync(self):
        """Wait until the server has handled everything this client sent so far."""
        self.line("/balance")
        self.expect_text("tokens.", kind="money")

    def wait_closed(self, timeout=TIMEOUT):
        with self.arrived:
            self.arrived.wait_for(lambda: self.closed, timeout)
        return self.closed

    def texts(self):
        with self.arrived:
            return [str(m.get("text", "")) for m in self.messages]

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def auth(client, action, name, password):
    client.send({"type": "auth", "action": action, "username": name, "password": password})
    return client.expect(lambda m: m.get("type") == "auth_result")


class FakeFoundry:
    """A local stand-in for Microsoft Foundry's Responses API. Never the real thing."""

    def __init__(self):
        self.status = 200
        self.answer = "Hi from fake Hashbrown 🥔"
        self.delay = 0
        self.reject_reasoning = False  # answer 400 to requests that contain "reasoning"
        self.requests = []  # (headers, body) of every request
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append((dict(self.headers), body))
                time.sleep(fake.delay)
                status = 400 if fake.reject_reasoning and "reasoning" in body else fake.status
                reply = {"output": [{"type": "message", "content": [
                    {"type": "output_text", "text": fake.answer}]}]} if status == 200 else {"error": "boom"}
                data = json.dumps(reply).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_port}/openai/v1/responses"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def stop(self):
        self.http.shutdown()
        self.http.server_close()
