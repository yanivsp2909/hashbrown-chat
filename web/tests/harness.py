"""
Test harness: runs a COPY of the chat server in a temp folder plus the web bridge,
and gives tests a tiny fake "browser" that talks to the bridge like app.js does.
Your real chat_data.json is never touched.
"""
import http.client
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
SKIP = {"web", "chat_data.json", "chat_data.json.tmp", "hashbrown_config.json",
        "received_files", "__pycache__", ".git", ".claude", "graphify-out"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port, proc, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            raise RuntimeError(f"process exited early with code {proc.returncode}")
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"nothing listening on port {port} after {timeout}s")


class Stack:
    """Chat server copy + bridge, both on random free ports."""

    def __init__(self, max_sessions=4, fake_ai_port=None):
        """fake_ai_port: a FakeFoundry on 127.0.0.1 for the copy to use as Hashbrown (never the real AI)."""
        self.tmp = Path(tempfile.mkdtemp(prefix="hashbrown_test_"))
        self.chat_port, self.web_port = free_port(), free_port()
        self._copy_server()
        if fake_ai_port:
            (self.tmp / "hashbrown_config.json").write_text(json.dumps({
                "endpoint": f"http://127.0.0.1:{fake_ai_port}", "deployment": "fake-model",
                "api_key": "test-key"}), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "HASHBROWN_API_KEY"}
        env["PYTHONIOENCODING"] = "utf-8"
        self.chat_log = open(self.tmp / "chat_server.log", "w", encoding="utf-8")
        self.chat = subprocess.Popen([sys.executable, "server.py"], cwd=self.tmp, env=env,
                                     stdin=subprocess.DEVNULL, stdout=self.chat_log, stderr=subprocess.STDOUT)
        wait_port(self.chat_port, self.chat)
        self.web_log = open(self.tmp / "web_server.log", "w", encoding="utf-8")
        self.web = subprocess.Popen(
            [sys.executable, str(WEB / "web_server.py"), "--port", str(self.web_port),
             "--chat-port", str(self.chat_port), "--max-sessions", str(max_sessions)],
            env=env, stdin=subprocess.DEVNULL, stdout=self.web_log, stderr=subprocess.STDOUT)
        wait_port(self.web_port, self.web)

    def _copy_server(self):
        """Copy the chat server's Python files and move the copy to a free port on 127.0.0.1."""
        for item in ROOT.iterdir():
            if item.name in SKIP or item.name.startswith("."):
                continue
            if item.is_dir() and any(item.rglob("*.py")):
                shutil.copytree(item, self.tmp / item.name, ignore=shutil.ignore_patterns("__pycache__"))
            elif item.suffix == ".py":
                shutil.copy2(item, self.tmp / item.name)
        port_line = re.compile(r"^PORT = 8820\s*$", re.M)
        host_line = re.compile(r'^HOST = "0\.0\.0\.0"\s*$', re.M)
        moved = False
        for path in self.tmp.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if port_line.search(text):
                text = port_line.sub(f"PORT = {self.chat_port}", text)
                text = host_line.sub('HOST = "127.0.0.1"', text)
                path.write_text(text, encoding="utf-8")
                moved = True
        if not moved:
            raise RuntimeError("Couldn't find the line 'PORT = 8820' in the chat server's .py files. "
                               "The test needs it to run a copy of the server on another port.")
        if not (self.tmp / "server.py").exists():
            raise RuntimeError("server.py is missing: the test starts the chat server with 'python server.py'.")

    def source_text(self):
        return "\n".join(p.read_text(encoding="utf-8") for p in self.tmp.rglob("*.py"))

    def stop(self):
        for proc in (self.web, self.chat):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.chat_log.close()
        self.web_log.close()
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------- HTTP helpers

def request(port, method, path, body=None, headers=None, raw=None):
    """Returns (status, headers dict, parsed JSON or raw bytes)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    all_headers = {"Host": f"127.0.0.1:{port}"}
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        all_headers["Content-Type"] = "application/json"
        all_headers["X-Hashbrown"] = "1"
    all_headers.update(headers or {})
    try:
        conn.request(method, path, body=data, headers=all_headers)
        resp = conn.getresponse()
        payload = resp.read()
    finally:
        conn.close()
    try:
        payload = json.loads(payload)
    except ValueError:
        pass
    return resp.status, {k.lower(): v for k, v in resp.getheaders()}, payload


class Stream:
    """A minimal EventSource: collects every SSE event into a queue."""

    def __init__(self, port, sid, last=0):
        self.conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        self.conn.request("GET", f"/api/events?sid={sid}&last={last}", headers={"Host": f"127.0.0.1:{port}"})
        self.resp = self.conn.getresponse()
        self.status = self.resp.status
        self.events = queue.Queue()
        self.seen = []
        if self.status == 200:
            threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        event, data, event_id = "message", [], None
        try:
            for raw in self.resp:
                line = raw.decode("utf-8").rstrip("\r\n")
                if not line:
                    if data:
                        self.events.put({"event": event, "id": event_id, "data": json.loads("\n".join(data))})
                    event, data, event_id = "message", [], None
                elif line.startswith("data:"):
                    data.append(line[5:].lstrip(" "))
                elif line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("id:"):
                    event_id = int(line[3:].strip())
        except (OSError, ValueError):
            pass
        self.events.put(None)

    def wait_for(self, predicate, timeout=10, what="a matching event"):
        end = time.time() + timeout
        while time.time() < end:
            try:
                item = self.events.get(timeout=max(0.01, end - time.time()))
            except queue.Empty:
                break
            if item is None:
                break
            self.seen.append(item)
            if predicate(item):
                return item
        recent = [json.dumps(e["data"], ensure_ascii=False)[:160] for e in self.seen[-8:]]
        raise AssertionError(f"Timed out waiting for {what}. Last events:\n  " + "\n  ".join(recent))

    def close(self):
        self.conn.close()


def is_msg(text_start=None, kind=None, type_="msg"):
    def check(e):
        d = e["data"]
        return (e["event"] == "message" and d.get("type") == type_
                and (kind is None or d.get("kind") == kind)
                and (text_start is None or str(d.get("text", "")).startswith(text_start)))
    return check


class Browser:
    """One browser tab: a bridge session and its event stream."""

    def __init__(self, port):
        self.port = port
        status, _, body = request(port, "POST", "/api/session", body={})
        if status != 200:
            raise AssertionError(f"couldn't create a session: {status} {body}")
        self.sid = body["sid"]
        self.stream = Stream(port, self.sid)
        self.recent = []  # times of recent non-move lines

    def send(self, obj):
        status, _, body = request(self.port, "POST", "/api/send", body=obj, headers={"X-Session-Id": self.sid})
        return status, body

    def line(self, text):
        if not text.isdigit():  # the server allows 8 messages per 5 s (game moves don't count)
            self.recent = [t for t in self.recent if time.time() - t < 5.5]
            if len(self.recent) >= 6:
                time.sleep(5.5 - (time.time() - self.recent[0]))
            self.recent.append(time.time())
        status, body = self.send({"type": "line", "text": text})
        assert status == 202, f"sending {text!r} failed: {status} {body}"

    def auth(self, username, password, action="login", features=None):
        packet = {"type": "auth", "action": action, "username": username, "password": password}
        if features is not None:
            packet["features"] = features
        status, body = self.send(packet)
        assert status == 202, f"auth send failed: {status} {body}"
        return self.stream.wait_for(lambda e: e["data"].get("type") == "auth_result", what="auth_result")["data"]

    def wait(self, predicate, timeout=10, what="a matching event"):
        return self.stream.wait_for(predicate, timeout, what)["data"]

    def close(self):
        request(self.port, "POST", "/api/close", body={}, headers={"X-Session-Id": self.sid})
        self.stream.close()
