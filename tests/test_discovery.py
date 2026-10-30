"""🔎 UDP auto-discovery: a client shouts "is there a chat server?" on the LAN, and servers answer."""
import json
import socket

import pytest

import client
from chatserver import config, discovery


@pytest.fixture
def responder():
    """The server's discovery answerer on a free UDP port of 127.0.0.1. Yields that port."""
    sock = discovery.start_discovery("127.0.0.1", 0)
    yield sock.getsockname()[1]
    sock.close()


def ask(port, payload, timeout=1.0):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(payload, ("127.0.0.1", port))
        try:
            return json.loads(s.recvfrom(2048)[0])
        except socket.timeout:
            return None


def test_the_server_answers_a_discover_packet_with_its_ports(responder):
    reply = ask(responder, b'{"type": "discover"}')
    assert reply == {"type": "server", "name": config.SERVER_NAME, "port": config.PORT, "web_port": config.WEB_PORT}


@pytest.mark.parametrize("payload", [b"hello", b"{not json", b'{"type": "other"}', b"[1, 2]", b"x" * 600])
def test_anything_else_gets_no_answer(responder, payload):
    assert ask(responder, payload, timeout=0.3) is None


def test_the_answer_is_small_so_it_cant_be_used_to_flood_someone(responder):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(1)
        s.sendto(b'{"type":"discover"}', ("127.0.0.1", responder))
        assert len(s.recvfrom(2048)[0]) < 200


def test_the_client_finds_the_server_and_uses_the_address_it_answered_from(responder):
    found = client.discover(targets=[("127.0.0.1", responder)], timeout=0.5)
    assert found == [("127.0.0.1", config.SERVER_NAME)]


def test_the_client_finds_nothing_when_no_server_answers():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        silent_port = s.getsockname()[1]     # bound but never answers
        assert client.discover(targets=[("127.0.0.1", silent_port)], timeout=0.3) == []


def test_with_no_server_found_the_client_asks_for_the_ip(monkeypatch):
    monkeypatch.setattr(client, "discover", lambda **kwargs: [])
    monkeypatch.setattr(client.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "192.168.1.20")
    assert client.find_server() == "192.168.1.20"


def test_with_no_server_found_and_no_keyboard_it_uses_this_computer(monkeypatch):
    monkeypatch.setattr(client, "discover", lambda **kwargs: [])
    monkeypatch.setattr(client.sys.stdin, "isatty", lambda: False, raising=False)
    assert client.find_server() == "127.0.0.1"


def test_one_server_found_without_a_keyboard_is_used_without_asking(monkeypatch):
    monkeypatch.setattr(client, "discover", lambda **kwargs: [("10.0.0.7", "Hashbrown Chat")])
    monkeypatch.setattr(client.sys.stdin, "isatty", lambda: False, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("asked"))
    assert client.find_server() == "10.0.0.7"


def test_deeply_nested_garbage_doesnt_kill_the_answerer(responder):
    assert ask(responder, b"[" * 500, timeout=0.3) is None
    assert ask(responder, b'{"type": "discover"}')["type"] == "server"      # still alive


def test_a_single_server_found_at_a_keyboard_is_confirmed_first(monkeypatch):
    monkeypatch.setattr(client, "discover", lambda **kwargs: [("10.0.0.7", "Hashbrown Chat")])
    monkeypatch.setattr(client.sys.stdin, "isatty", lambda: True, raising=False)
    answers = iter(["n", "192.168.1.20"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert client.find_server() == "192.168.1.20"     # said no, then typed the right IP


def test_at_most_nine_servers_are_listed(responder):
    found = client.discover(targets=[("127.0.0.1", responder)] * 1, timeout=0.3)
    assert len(found) <= 9
    assert client.MAX_SERVERS == 9
