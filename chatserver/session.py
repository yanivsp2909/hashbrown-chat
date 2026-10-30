"""
🔌 One connected person: their socket, the writer thread and reading JSON lines.
"""
import json
import queue
import socket
import threading
import time
import traceback
from collections import deque

from chatserver import config, textutil


# ---------------------------------------------------------------- one connected person

class Client:
    def __init__(self, sock, address):
        self.sock = sock
        self.address = address
        self.key = None          # login name once logged in
        self.room = "lobby"
        self.quitting = False
        self.login_deadline = time.time() + config.LOGIN_TIMEOUT  # strangers must log in before this
        self.recent = deque()    # times of recent messages, for spam protection
        # Sending goes through a queue + its own thread, so a slow connection
        # can never freeze the server while it holds the lock.
        self.outbox = queue.Queue(maxsize=config.OUTBOX_LIMIT)
        self.writer = threading.Thread(target=self._write_loop, daemon=True)
        self.writer.start()

    def _write_loop(self):
        while True:
            obj = self.outbox.get()
            if obj is None:
                return
            try:
                # "replace": a broken character becomes "?" instead of killing this thread
                self.sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8", "replace"))
            except OSError:  # the connection is gone: make the reading side notice too
                hang_up(self)
                return
            except Exception:  # a bug in one message must never leave this person deaf
                textutil.log("[SERVER] Error while sending:\n" + traceback.format_exc())
                hang_up(self)
                return

    def send(self, obj):
        try:
            self.outbox.put_nowait(obj)
        except queue.Full:
            # They stopped reading. Dropping messages would break their game board, so disconnect them.
            hang_up(self)

    def say(self, text, kind="system"):
        self.send({"type": "msg", "kind": kind, "text": text})

    def kick(self, text):
        """Tell them why, then hang up half a second later (so the message gets there first)."""
        self.say(text, "error")
        threading.Timer(0.5, hang_up, args=(self,)).start()

    def close(self):
        try:
            self.outbox.put_nowait(None)
        except queue.Full:
            pass  # the writer is stuck or gone; closing the socket below stops it
        self.writer.join(timeout=1)  # let the last messages go out first
        try:
            self.sock.close()
        except OSError:
            pass


def recv_lines(sock, client):
    """Yield complete lines from the socket (one JSON message per line)."""
    buffer = bytearray()
    while True:
        if client.key is None:  # not logged in: the clock keeps running, sending bytes doesn't reset it
            left = client.login_deadline - time.time()
            if left <= 0:
                return
            sock.settimeout(left)
        chunk = sock.recv(65536)
        if not chunk:  # empty = the other side closed the connection
            return
        start = len(buffer)
        buffer += chunk
        while True:
            end = buffer.find(b"\n", start)
            if end == -1:
                break
            line = bytes(buffer[:end])
            del buffer[:end + 1]
            start = 0
            yield line
        limit = config.MAX_LINE if client.key else config.MAX_LOGIN_LINE  # strangers can't send 4 MB
        if len(buffer) > limit:  # no newline that far: broken or abusive client
            return


def parse_message(raw):
    """One line from the network -> a dict, or None if it isn't a JSON object."""
    try:
        msg = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):  # RecursionError: [[[[... nested very deep
        return None
    return msg if isinstance(msg, dict) else None


# ---------------------------------------------------------------- chat lines

def hang_up(client):
    try:
        client.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
