"""🌐 server.py starts the website (web/web_server.py) as a second program, and stops it again."""
import os
import socket
import sys

import pytest

from chatserver import config, website


class FakeProcess:
    """Stands in for subprocess.Popen, so no real website starts during the tests."""
    started = []

    def __init__(self, args, env=None, cwd=None):
        self.args, self.env, self.cwd = args, env, cwd
        self.stopped = self.killed = False
        FakeProcess.started.append(self)

    def poll(self):
        return 0 if self.stopped else None

    def terminate(self):
        self.stopped = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


@pytest.fixture
def fake_popen(monkeypatch):
    FakeProcess.started = []
    monkeypatch.setattr(website.subprocess, "Popen", FakeProcess)
    monkeypatch.delenv("HASHBROWN_START_WEBSITE", raising=False)
    monkeypatch.setattr(config, "WEB_PORT", free_port())
    return FakeProcess


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_it_starts_web_server_py_with_this_python_and_the_chat_port(fake_popen):
    process = website.start_website(chat_port=8820)
    assert process is fake_popen.started[0]
    assert process.args[0] == sys.executable
    assert process.args[1] == os.path.join(config.BASE_DIR, "web", "web_server.py")
    assert process.args[2:] == ["--port", str(config.WEB_PORT), "--chat-port", "8820"]


def test_the_website_never_gets_the_secrets(fake_popen, monkeypatch):
    monkeypatch.setenv("HASHBROWN_API_KEY", "test-key")
    monkeypatch.setenv("HASHBROWN_ADMIN_PASSWORD", "test-password")
    process = website.start_website(chat_port=8820)
    assert "HASHBROWN_API_KEY" not in process.env
    assert "HASHBROWN_ADMIN_PASSWORD" not in process.env
    assert process.env.get("PATH") == os.environ.get("PATH")  # everything else is passed on


def test_switched_off_in_config_or_by_the_environment(fake_popen, monkeypatch, capsys):
    monkeypatch.setattr(config, "START_WEBSITE", False)
    assert website.start_website(chat_port=8820) is None
    monkeypatch.setattr(config, "START_WEBSITE", True)
    monkeypatch.setenv("HASHBROWN_START_WEBSITE", "0")
    assert website.start_website(chat_port=8820) is None
    assert fake_popen.started == []


def test_no_web_folder_means_no_website_but_the_chat_still_runs(fake_popen, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "BASE_DIR", str(tmp_path))
    assert website.start_website(chat_port=8820) is None
    assert fake_popen.started == []
    assert "web/web_server.py" in capsys.readouterr().out


def test_a_busy_website_port_is_left_alone(fake_popen, capsys):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", config.WEB_PORT))
        busy.listen()
        assert website.start_website(chat_port=8820) is None
    assert fake_popen.started == []
    assert f"Port {config.WEB_PORT} is busy" in capsys.readouterr().out


def test_stopping_the_website(fake_popen):
    process = website.start_website(chat_port=8820)
    website.stop_website(process)
    assert process.stopped
    website.stop_website(None)  # nothing started: nothing to do
