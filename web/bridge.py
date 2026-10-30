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
MAX_FEATURES, MAX_FEATURE_LENGTH = 8, 20   # the optional "features" list in the login packet
LOG_MAX_EVENTS = 1000        # events kept per session for replay after a reload
LOG_MAX_BYTES = 6 * 1024 * 1024
XRAY_MAX_TEXT = 2000           # 🔬 bytes of each raw chunk shown in the Packet X-ray (big files are cut)
CHUNK_B64 = 1_400_000          # 📦 one chunk of a big file, after base64 (as in the chat server)
LIVE_ONLY_MAX_BYTES = 8 * 1024 * 1024    # 📦 big file chunks waiting for a tab (never replayed; one is on its way at a time)
XRAY_KEEP = 100                # 🔬 X-ray events kept in the replay log, so chat messages aren't pushed out
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


def clean_features(value):
    """The optional list of short feature names (same limits as the chat server: 8 names, 20 characters)."""
    if (not isinstance(value, list) or len(value) > MAX_FEATURES
            or not all(isinstance(f, str) and len(f) <= MAX_FEATURE_LENGTH for f in value)):
        raise BridgeError(400, "Features must be a short list of short words.")
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
        auth = {"type": "auth", "action": msg["action"],
                "username": clean(msg.get("username"), 64, "Username"),
                "password": clean(msg.get("password"), 128, "Password")}
        if "features" in msg:   # optional: what this browser understands, like ["stream"]
            auth["features"] = clean_features(msg["features"])
        return auth
    if kind not in ("line", "file", "ping", "typing", "react", "file_start", "file_chunk", "file_cancel"):
        raise BridgeError(400, "Unknown message type.")
    if not logged_in:
        raise BridgeError(403, "Log in first.")
    if kind == "typing":   # ⌨️ no fields at all
        return {"type": "typing"}
    if kind == "react":    # 😂 a message id and one short emoji (the server checks it's an allowed one)
        message_id = msg.get("id")
        if not isinstance(message_id, int) or isinstance(message_id, bool):
            raise BridgeError(400, "Bad reaction.")
        return {"type": "react", "id": message_id, "emoji": clean(msg.get("emoji"), 8, "Emoji")}
    if kind == "ping":   # 🏓 only a number travels with it
        t = msg.get("t")
        return {"type": "ping", **({"t": t} if isinstance(t, (int, float)) and not isinstance(t, bool) else {})}
    if kind == "line":
        return {"type": "line", "text": clean(msg.get("text"), MAX_TEXT, "Message")}
    if kind in ("file_start", "file_chunk", "file_cancel"):
        return big_file_packet(kind, msg)
    data = msg.get("data")
    if not isinstance(data, str) or len(data) > MAX_FILE_B64:
        raise BridgeError(413, "Files must be 2 MB or less.")
    if len(data) % 4 or not BASE64.fullmatch(data):
        raise BridgeError(400, "That file didn't encode properly.")
    return {"type": "file", "to": clean(msg.get("to"), 32, "Name"),
            "filename": clean(msg.get("filename"), 255, "File name"), "data": data}


def whole_number(value, what):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BridgeError(400, f"Bad {what}.")
    return value


def big_file_packet(kind, msg):
    """📦 A big file in chunks (the chat server checks the sizes and the order)."""
    packet = {"type": kind, "id": clean(msg.get("id"), 40, "Transfer id")}
    if kind == "file_start":
        packet.update(to=clean(msg.get("to"), 32, "Name"), filename=clean(msg.get("filename"), 255, "File name"),
                      size=whole_number(msg.get("size"), "size"), chunks=whole_number(msg.get("chunks"), "chunk count"))
    elif kind == "file_chunk":
        data = msg.get("data")
        if not isinstance(data, str) or len(data) > CHUNK_B64 or len(data) % 4 or not BASE64.fullmatch(data):
            raise BridgeError(400, "That piece of the file didn't encode properly.")
        packet.update(index=whole_number(msg.get("index"), "chunk number"), data=data)
    return packet


def read_lines(sock, on_chunk=None):
    """Yield complete lines from the chat server (one JSON message per line).
    on_chunk(bytes) sees every raw recv() result first: TCP chunks don't line up with messages."""
    buffer = bytearray()
    while True:
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            continue
        if not chunk:
            return
        if on_chunk:
            on_chunk(chunk)
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
        self.xray = False            # 🔬 the tab's Packet X-ray is open: show it the raw TCP traffic too
        self.xray_ids = deque()      # 🔬 ids of the x-ray events still in the replay log
        self.live_only = deque()     # 📦 (id, json text) sent once to the tab, never replayed: big file chunks
        self.live_only_size = 0
        self.trimmed_upto = 0        # the newest event id the replay log had to drop (0 = none)
        self.auth_pending = False    # one login attempt at a time, so guesses can't be pipelined
        threading.Thread(target=self._read_loop, daemon=True).start()

    # ----- chat server -> browser

    def _read_loop(self):
        reason = "The chat server closed the connection."
        try:
            for raw in read_lines(self.sock, self._xray_in):
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
                text = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
                if msg.get("type") == "file_chunk":   # 📦 1 MB each: kept out of the replay log
                    self._append_live_only(text)
                else:
                    self._append(text)
        except OSError:
            reason = "Lost the connection to the chat server."
        self.end(reason)

    def _append(self, text):
        with self.cond:
            self.last_id += 1
            self.events.append((self.last_id, text))
            self.size += len(text)
            while len(self.events) > 1 and (len(self.events) > LOG_MAX_EVENTS or self.size > LOG_MAX_BYTES):
                dropped_id, dropped_text = self.events.popleft()
                self.size -= len(dropped_text)
                self.trimmed_upto = dropped_id
            self.cond.notify_all()

    def _append_live_only(self, text):
        with self.cond:
            self.last_id += 1
            self.live_only.append((self.last_id, text))
            self.live_only_size += len(text)
            while self.live_only and self.live_only_size > LIVE_ONLY_MAX_BYTES:   # nobody's reading: give up
                self.live_only_size -= len(self.live_only.popleft()[1])
            self.cond.notify_all()

    def forget_sent(self, last_id):
        """The tab got everything up to last_id: live-only events are done. Call while holding cond."""
        while self.live_only and self.live_only[0][0] <= last_id:
            self.live_only_size -= len(self.live_only.popleft()[1])

    def since(self, last_id):
        """Events after last_id, and whether some were already dropped. Call while holding cond."""
        missed = sorted([e for e in self.events if e[0] > last_id] + [e for e in self.live_only if e[0] > last_id])
        gap = self.trimmed_upto > last_id   # (ids also skip for x-ray and live-only events: that's no gap)
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

    # ----- 🔬 Packet X-ray: the raw bytes, exactly as TCP delivered them (shown only to this tab)

    def _xray(self, direction, data):
        if not self.xray:
            return
        with self.cond:   # keep only the newest XRAY_KEEP x-ray events: the log is for chat replay first
            if len(self.xray_ids) >= XRAY_KEEP:
                oldest = self.xray_ids.popleft()
                for event in [e for e in self.events if e[0] == oldest]:   # (it may already be trimmed)
                    self.events.remove(event)
                    self.size -= len(event[1])
            self.xray_ids.append(self.last_id + 1)   # the id _append is about to give it
        self._append(json.dumps({"type": "xray", "dir": direction, "bytes": len(data), "time": time.time(),
                                 "text": data[:XRAY_MAX_TEXT].decode("utf-8", "replace")},
                                ensure_ascii=False, separators=(",", ":")))

    def _xray_in(self, chunk):
        self._xray("in", chunk)

    def forward(self, msg):
        if self.dead:
            raise BridgeError(410, self.dead)
        if isinstance(msg, dict) and msg.get("type") == "xray":  # for the bridge itself, never sent on
            self.xray = msg.get("on") is True
            return
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
            if clean_msg["type"] != "auth":   # a login carries a password: never echo that, not even to yourself
                self._xray("out", line)
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
