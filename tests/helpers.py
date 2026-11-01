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


def auth(client, action, name, password, features=None):
    packet = {"type": "auth", "action": action, "username": name, "password": password}
    if features is not None:
        packet["features"] = features
    client.send(packet)
    return client.expect(lambda m: m.get("type") == "auth_result")


class FakeFoundry:
    """A local stand-in for Microsoft Foundry's Responses API, speaking what the openai package
    expects: Server-Sent Events (response.output_text.delta ... response.completed). Never the real thing.

    Settings a test can change:
      answer / pieces   the text, sent as one piece or as the list of pieces
      status            answer with this HTTP status instead (a JSON error body)
      reject_reasoning  answer 400 to requests that contain "reasoning"
      break_after       after this many pieces, break the stream...
      break_with        ..."failed" (response.failed event), "error" (error event), "incomplete"
                        or "drop" (just hang up)
      delay             seconds to wait before answering; piece_delay between pieces
      answers           a list of texts: each request takes the next one (then `answer` again)
      reject_text_format  answer 400 to requests that ask for a JSON format ("text")
    """

    def __init__(self):
        self.status = 200
        self.answer = "Hi from fake Hashbrown 🥔"
        self.pieces = None
        self.delay = 0
        self.piece_delay = 0
        self.reject_reasoning = False
        self.reject_text_format = False
        self.answers = []
        self.break_after = None
        self.break_with = "failed"
        self.requests = []  # (headers, body) of every request
        fake = self

        def event(handler, kind, number, **fields):
            data = json.dumps({"type": kind, "sequence_number": number, **fields}, ensure_ascii=False)
            handler.wfile.write(f"event: {kind}\ndata: {data}\n\n".encode("utf-8"))
            handler.wfile.flush()

        def response_object(text, status):
            return {"id": "resp_1", "object": "response", "created_at": 0, "model": "fake-model", "status": status,
                    "output": [{"id": "msg_1", "type": "message", "role": "assistant", "status": status,
                                "content": [{"type": "output_text", "text": text, "annotations": []}]}],
                    "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
                    "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                              "input_tokens_details": {"cached_tokens": 0},
                              "output_tokens_details": {"reasoning_tokens": 0}}}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append((dict(self.headers), body))
                time.sleep(fake.delay)
                status = 400 if fake.reject_reasoning and "reasoning" in body else fake.status
                if fake.reject_text_format and "text" in body:
                    status = 400
                if status != 200:
                    data = json.dumps({"error": {"message": "boom", "type": "fake_error", "code": None}}).encode()
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                try:
                    self.stream_answer()
                except OSError:  # the server hung up on us (it has read enough)
                    pass

            def stream_answer(self):
                pieces = fake.pieces if fake.pieces is not None else [fake.answers.pop(0) if fake.answers else fake.answer]
                number = 0
                for number, piece in enumerate(pieces, 1):
                    if fake.break_after is not None and number > fake.break_after:
                        break
                    event(self, "response.output_text.delta", number, item_id="msg_1", output_index=0,
                          content_index=0, delta=piece)
                    time.sleep(fake.piece_delay)
                else:
                    event(self, "response.completed", number + 1, response=response_object("".join(pieces), "completed"))
                    return
                if fake.break_with == "failed":
                    event(self, "response.failed", number + 1, response=response_object("", "failed"))
                elif fake.break_with == "incomplete":
                    event(self, "response.incomplete", number + 1, response=response_object("", "incomplete"))
                elif fake.break_with == "error":
                    event(self, "error", number + 1, code="server_error", message="boom", param=None)

            def log_message(self, *args):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_port}/openai/v1"  # the openai package's base_url
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def stop(self):
        self.http.shutdown()
        self.http.server_close()
