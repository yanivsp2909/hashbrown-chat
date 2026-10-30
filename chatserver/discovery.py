"""
🔎 UDP auto-discovery: lets a client find the server on the LAN without typing an IP address.

The client sends ONE small UDP packet to the broadcast address (everyone on the Wi-Fi gets it):
    {"type": "discover"}
Every Hashbrown server that hears it answers the sender directly:
    {"type": "server", "name": "Hashbrown Chat", "port": 8820, "web_port": 8080}
The client takes the server's IP from where the answer came from.

Why UDP? There's no connection yet (we don't know who to connect to), and broadcast only exists in UDP.
Safety: only that exact request gets an answer, the answer is tiny and fixed (so nobody can use us to
flood someone else with big replies), and we answer at most DISCOVERY_MAX_PER_SECOND times a second.
"""
import json
import socket
import threading
import time

from chatserver import config, textutil

MAX_REQUEST = 512   # bytes: a real request is about 20


def answer():
    return json.dumps({"type": "server", "name": config.SERVER_NAME, "port": config.PORT,
                       "web_port": config.WEB_PORT}).encode()


def is_request(data):
    if len(data) > MAX_REQUEST:
        return False
    try:
        packet = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    return isinstance(packet, dict) and packet.get("type") == "discover"


def serve(sock):
    """Answer discover packets until the socket is closed."""
    recent = []   # times of recent answers, for the rate limit
    while True:
        try:
            data, sender = sock.recvfrom(MAX_REQUEST + 1)
        except OSError:
            return  # the socket was closed: the server is stopping
        if not is_request(data):
            continue
        now = time.time()
        recent = [t for t in recent if now - t < 1]
        if len(recent) >= config.DISCOVERY_MAX_PER_SECOND:
            continue
        recent.append(now)
        try:
            sock.sendto(answer(), sender)
        except OSError:
            pass  # that client is already gone


def start_discovery(host=None, port=None):
    """Open the UDP socket and answer in a background thread. Returns the socket (close it to stop),
    or None if the port is taken (the chat still works, people just type the IP)."""
    host = config.HOST if host is None else host
    port = config.DISCOVERY_PORT if port is None else port
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((host, port))
    except OSError as e:
        sock.close()
        textutil.log(f"[SERVER] 🔎 Can't listen for discovery on UDP port {port} ({e}). "
                     "Friends can still connect by typing your IP.")
        return None
    threading.Thread(target=serve, args=(sock,), daemon=True).start()
    return sock
