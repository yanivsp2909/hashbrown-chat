"""
🧪 Shared test helpers: a real server on a free port, fake clients, and a fake Hashbrown AI.

Safety, for every single test:
- the server saves to a temp chat_data.json and reads a temp hashbrown_config.json
- HASHBROWN_API_KEY and HASHBROWN_ADMIN_PASSWORD are removed from the environment
- any web request that doesn't go to 127.0.0.1 fails the test, so the real AI is never called
"""
import os
import threading
import urllib.request

import pytest

import server
from helpers import FakeClient, FakeFoundry, auth


# ---------------------------------------------------------------- isolation

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.delenv("HASHBROWN_API_KEY", raising=False)
    monkeypatch.delenv("HASHBROWN_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(server, "DATA_FILE", str(tmp_path / "chat_data.json"))
    monkeypatch.setattr(server, "HASHBROWN_CONFIG", str(tmp_path / "hashbrown_config.json"))
    monkeypatch.setattr(server, "SPAM_LIMIT", 1000)  # tests type fast; the spam test sets it back
    monkeypatch.setattr(server, "ACCEPT_WAKEUP", 0.1)  # stop each test's server quickly
    for path in (server.DATA_FILE, server.HASHBROWN_CONFIG):
        assert os.path.realpath(path).startswith(os.path.realpath(str(tmp_path)))

    real_urlopen = urllib.request.urlopen

    def local_only(request, *args, **kwargs):
        url = getattr(request, "full_url", request)
        if not url.startswith("http://127.0.0.1:"):
            raise AssertionError(f"tests may only call 127.0.0.1, not {url}")
        return real_urlopen(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", local_only)
    server.reset_state()
    yield
    server.reset_state()


# ---------------------------------------------------------------- the real server

@pytest.fixture
def chat_server():
    """Starts server.py's server on a free port (no income/quiz loops, no console). Yields the port."""
    listener = server.start_server("127.0.0.1", 0, run_loops=False, run_console=False)
    assert listener is not None
    thread = threading.Thread(target=server.serve_forever, args=(listener,), daemon=True)
    thread.start()
    yield listener.getsockname()[1]
    with server.lock:
        clients = list(server.online.values())
    for c in clients:
        server.hang_up(c)
    listener.close()
    thread.join(5)  # let serve_forever finish shutting down before the next test starts
    assert not thread.is_alive()


@pytest.fixture
def connect(chat_server):
    """connect() -> a new FakeClient that isn't logged in yet."""
    made = []

    def make():
        client = FakeClient(chat_server)
        made.append(client)
        return client

    yield make
    for client in made:
        client.close()


@pytest.fixture
def user(connect):
    """user("adi") -> a FakeClient that registered (or logged in) and is in the lobby."""
    def make(name, password="pass1234", action="register"):
        client = connect()
        result = auth(client, action, name, password)
        assert result["ok"], result
        client.expect(lambda m: m.get("type") == "history")
        client.name = name
        return client
    return make


# ---------------------------------------------------------------- fake Hashbrown AI

@pytest.fixture
def fake_hashbrown(chat_server):
    """Wakes Hashbrown up, pointed at a FakeFoundry on 127.0.0.1."""
    foundry = FakeFoundry()
    server.hashbrown = {"deployment": "fake-model", "api_key": "test-key", "url": foundry.url}
    yield foundry
    foundry.stop()
