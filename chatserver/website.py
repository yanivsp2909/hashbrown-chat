"""
🌐 Starts the website (web/web_server.py) next to the chat server, as a second program, and stops it again.

The website is its own program because it's a different kind of server (HTTP for browsers).
It connects to the chat server over TCP like any other client, so it never sees the AI key.
"""
import os
import socket
import subprocess
import sys

from chatserver import config, textutil

SECRETS = ("HASHBROWN_API_KEY", "HASHBROWN_ADMIN_PASSWORD")   # the website must never get these


def is_port_busy(port):
    """True if something already answers on this port on this computer (maybe the website is already running)."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def start_website(chat_port):
    """Start web/web_server.py. Returns the running program, or None if it didn't start (the chat works either way)."""
    if not config.START_WEBSITE or os.environ.get("HASHBROWN_START_WEBSITE") == "0":
        return None
    script = os.path.join(config.BASE_DIR, "web", "web_server.py")
    if not os.path.exists(script):
        textutil.log("[WEB] No web/web_server.py next to server.py, so no website. The chat still works.")
        return None
    if is_port_busy(config.WEB_PORT):
        textutil.log(f"[WEB] Port {config.WEB_PORT} is busy (is the website already running?), "
                     "so I'm not starting a second one.")
        return None
    env = {name: value for name, value in os.environ.items() if name not in SECRETS}
    try:
        return subprocess.Popen([sys.executable, script, "--port", str(config.WEB_PORT), "--chat-port", str(chat_port)],
                                env=env, cwd=config.BASE_DIR)
    except OSError as e:
        textutil.log(f"[WEB] Couldn't start the website ({type(e).__name__}). The chat still works.")
        return None


def stop_website(process):
    """Ask the website to stop, and make sure it really does."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
