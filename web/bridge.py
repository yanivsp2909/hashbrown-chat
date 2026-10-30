"""
🌉 Sessions for the website: every browser tab gets its own TCP connection to the chat server.

Browser -> server: validate(), then Session.forward() writes one JSON line to the chat server.
Server -> browser: a reader thread puts every line from the chat server into the session's
event log, and the /api/events stream in web_server.py sends them on (and replays what a
reloaded tab missed).
"""
import json
import re
import secrets
import socket
import threading
import time
from collections import deque

MAX_LINE = 4 * 1024 * 1024   # same limit as the chat server
MAX_TEXT = 500               # longest chat line the server accepts
MAX_FILE_B64 = 2_800_000     # a 2 MB file after base64
LOG_MAX_EVENTS = 1000        # events kept per session for replay after a reload
LOG_MAX_BYTES = 6 * 1024 * 1024
DETACHED_GRACE = 90          # seconds a session lives with no tab attached (reload / phone in pocket)
LOGIN_GRACE = 120            # seconds to log in before an unused session is closed
CLOSED_LINGER = 30           # seconds a dead session is kept so its tab can read why it died
SESSIONS_PER_IP = 8
CREATES_PER_MINUTE = 30      # new sessions per IP per minute
LOGIN_FAILS, LOGIN_WINDOW = 8, 300   # failed logins per IP per 5 minutes
SENDS, SENDS_WINDOW = 20, 5          # messages per session per 5 seconds
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
BASE64 = re.compile(r"[A-Za-z0-9+/]*={0,2}")


class BridgeError(Exception):
    """Something the browser did wrong, with the HTTP status to answer with."""

    def __init__(self, status, text):
        super().__init__(text)
        self.status = status
        self.text = text


def allow(times, limit, window):
    """Sliding-window rate limit on a deque of timestamps. Records the attempt if allowed."""
    now = time.monotonic()
    while times and now - times[0] > window:
        times.popleft()
    if len(times) >= limit:
        return False
    times.append(now)
    return True


def to_line(obj):
    """One JSON line for the chat server. json.dumps escapes newlines, so it can never split."""
    try:
        data = (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    except UnicodeEncodeError:  # a lone surrogate from a "\ud800" escape
        raise BridgeError(400, "That text has broken characters.") from None
    if len(data) > MAX_LINE:
        raise BridgeError(413, "That's too big.")
    return data


def clean(value, limit, what):
    if not isinstance(value, str):
        raise BridgeError(400, f"{what} must be text.")
    value = CONTROL_CHARS.sub("", value)
    if len(value) > limit:
        raise BridgeError(400, f"{what} is too long ({limit} characters max).")
    return value


def validate(msg, logged_in):
    """Turn what the browser sent into a fresh dict with only the fields the chat server knows."""
    if not isinstance(msg, dict):
        raise BridgeError(400, "Expected a JSON object.")
    kind = msg.get("type")
    if kind == "auth":
        if logged_in:
            raise BridgeError(400, "You're already logged in.")
        if msg.get("action") not in ("login", "register"):
            raise BridgeError(400, "Bad login request.")
        return {"type": "auth", "action": msg["action"],
                "username": clean(msg.get("username"), 64, "Username"),
                "password": clean(msg.get("password"), 128, "Password")}
    if kind not in ("line", "file"):
        raise BridgeError(400, "Unknown message type.")
    if not logged_in:
        raise BridgeError(403, "Log in first.")
    if kind == "line":
        return {"type": "line", "text": clean(msg.get("text"), MAX_TEXT, "Message")}
    data = msg.get("data")
    if not isinstance(data, str) or len(data) > MAX_FILE_B64:
        raise BridgeError(413, "Files must be 2 MB or less.")
    if len(data) % 4 or not BASE64.fullmatch(data):
        raise BridgeError(400, "That file didn't encode properly.")
    return {"type": "file", "to": clean(msg.get("to"), 32, "Name"),
            "filename": clean(msg.get("filename"), 255, "File name"), "data": data}


def read_lines(sock):
    """Yield complete lines from the chat server (one JSON message per line)."""
    buffer = bytearray()
    while True:
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            continue
        if not chunk:
            return
        start = len(buffer)
        buffer += chunk
        while (end := buffer.find(b"\n", start)) != -1:
            line = bytes(buffer[:end])
            del buffer[:end + 1]
            start = 0
            yield line
        if len(buffer) > MAX_LINE:
            return


class Session:
    """One browser tab <-> one TCP connection to the chat server."""

    def __init__(self, sock, ip):
        self.sid = secrets.token_urlsafe(32)
        self.ip = ip
        self.sock = sock
        self.logged_in = False
        self.on_login_fail = None    # set by the Registry
        self.cond = threading.Condition()
        self.events = deque()        # (id, json text) from the chat server
        self.size = 0                # bytes in self.events
        self.last_id = 0
        self.dead = None             # why the connection ended, once it has
        self.dead_at = None
        self.stream = 0              # generation of the attached /api/events stream, 0 = none
        self.streams_started = 0
        self.created = self.detached_at = time.monotonic()
        self.send_lock = threading.Lock()
        self.rate_lock = threading.Lock()
        self.sends = deque()
        self.auth_pending = False    # one login attempt at a time, so guesses can't be pipelined
        threading.Thread(target=self._read_loop, daemon=True).start()

    # ----- chat server -> browser

    def _read_loop(self):
        reason = "The chat server closed the connection."
        try:
            for raw in read_lines(self.sock):
                try:
                    msg = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    continue
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") == "auth_result":
                    self.auth_pending = False
                    if msg.get("ok"):
                        self.logged_in = True
                    elif self.on_login_fail:
                        self.on_login_fail(self.ip)
                self._append(json.dumps(msg, ensure_ascii=False, separators=(",", ":")))
        except OSError:
            reason = "Lost the connection to the chat server."
        self.end(reason)

    def _append(self, text):
        with self.cond:
            self.last_id += 1
            self.events.append((self.last_id, text))
            self.size += len(text)
            while len(self.events) > 1 and (len(self.events) > LOG_MAX_EVENTS or self.size > LOG_MAX_BYTES):
                self.size -= len(self.events.popleft()[1])
            self.cond.notify_all()

    def since(self, last_id):
        """Events after last_id, and whether some were already dropped. Call while holding cond."""
        missed = [e for e in self.events if e[0] > last_id]
        gap = bool(self.events) and self.events[0][0] > last_id + 1
        return missed, gap

    # ----- the attached /api/events stream (newest one wins)

    def attach(self):
        with self.cond:
            self.streams_started += 1
            self.stream = self.streams_started
            self.detached_at = None
            self.cond.notify_all()  # wakes the old stream so it notices it was replaced
            return self.stream

    def detach(self, generation):
        with self.cond:
            if self.stream == generation:
                self.stream = 0
                self.detached_at = time.monotonic()

    # ----- browser -> chat server

    def forward(self, msg):
        if self.dead:
            raise BridgeError(410, self.dead)
        clean_msg = validate(msg, self.logged_in)
        line = to_line(clean_msg)
        with self.rate_lock:
            if not allow(self.sends, SENDS, SENDS_WINDOW):
                raise BridgeError(429, "🐢 Slow down a little!")
            if clean_msg["type"] == "auth":
                if self.auth_pending:
                    raise BridgeError(429, "⏳ Still checking your last try…")
                self.auth_pending = True
        with self.send_lock:
            try:
                self.sock.sendall(line)
            except OSError:
                self.end("Lost the connection to the chat server.")
                raise BridgeError(410, "Lost the connection to the chat server.") from None

    def end(self, reason):
        with self.cond:
            if self.dead is None:
                self.dead, self.dead_at = reason, time.monotonic()
            self.cond.notify_all()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    def expired(self, now):
        if self.dead:
            return now - self.dead_at > CLOSED_LINGER
        if not self.logged_in and now - self.created > LOGIN_GRACE:
            return True
        return self.detached_at is not None and now - self.detached_at > DETACHED_GRACE


class Registry:
    """All live sessions, the caps, and a cleanup thread."""

    def __init__(self, chat_address, max_sessions):
        self.chat_address = chat_address
        self.max_sessions = max_sessions
        self.lock = threading.Lock()
        self.sessions = {}
        self.reserved = {}      # ip -> sessions being connected right now (counted against the caps)
        self.creates = {}       # ip -> deque of times
        self.login_fails = {}   # ip -> deque of times
        threading.Thread(target=self._reap_loop, daemon=True).start()

    def create(self, ip):
        with self.lock:  # reserve the slot now: connecting takes a moment and others may be racing us
            if len(self.sessions) + sum(self.reserved.values()) >= self.max_sessions:
                raise BridgeError(503, "😵 The website is full right now. Try again in a minute.")
            mine = sum(1 for s in self.sessions.values() if s.ip == ip) + self.reserved.get(ip, 0)
            if mine >= SESSIONS_PER_IP:
                raise BridgeError(429, "Too many tabs open from this device. Close some first.")
            if not allow(self.creates.setdefault(ip, deque()), CREATES_PER_MINUTE, 60):
                raise BridgeError(429, "🐢 Too many reconnects. Wait a minute.")
            self.reserved[ip] = self.reserved.get(ip, 0) + 1
        try:
            sock = socket.create_connection(self.chat_address, timeout=3)
            sock.settimeout(30)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            session = Session(sock, ip)
            session.on_login_fail = self._login_failed
            with self.lock:
                self.sessions[session.sid] = session
            return session
        except OSError:
            raise BridgeError(503, "💤 The chat server isn't running. Ask the host to start server.py.") from None
        finally:
            with self.lock:
                self.reserved[ip] -= 1
                if not self.reserved[ip]:
                    del self.reserved[ip]

    def get(self, sid, ip):
        with self.lock:
            session = self.sessions.get(sid or "")
        if session is None or session.ip != ip:  # same answer either way: don't reveal valid ids
            raise BridgeError(404, "This session has ended. Reload the page.")
        return session

    def check_login_allowed(self, ip):
        with self.lock:
            fails = self.login_fails.setdefault(ip, deque())
            now = time.monotonic()
            while fails and now - fails[0] > LOGIN_WINDOW:
                fails.popleft()
            if len(fails) >= LOGIN_FAILS:
                raise BridgeError(429, "🔒 Too many wrong passwords. Wait 5 minutes.")

    def _login_failed(self, ip):
        with self.lock:
            self.login_fails.setdefault(ip, deque()).append(time.monotonic())

    def close(self, session, reason="You logged out."):
        with self.lock:
            self.sessions.pop(session.sid, None)
        session.end(reason)

    def close_all(self):
        with self.lock:
            sessions = list(self.sessions.values())
        for session in sessions:
            self.close(session, "The website was stopped.")

    def _reap_loop(self):
        while True:
            time.sleep(5)
            now = time.monotonic()
            with self.lock:
                old = [s for s in self.sessions.values() if s.expired(now)]
            for session in old:
                if session.expired(time.monotonic()):  # a tab may have come back in the meantime
                    self.close(session, "Disconnected after being away too long.")
            with self.lock:  # forget rate-limit history nobody needs anymore
                for table in (self.creates, self.login_fails):
                    for ip in [ip for ip, times in table.items() if not times or now - times[-1] > LOGIN_WINDOW]:
                        del table[ip]
