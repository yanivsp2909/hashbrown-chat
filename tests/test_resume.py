"""🔁 Reconnect and catch up. At login the server gives a "resume_token"; every packet it keeps for you has a
"seq" number (the last RESUME_KEEP of them, for RESUME_SECONDS). After a dropped connection the client logs in
with {"type": "auth", "action": "resume", "username", "token", "seq": the last one it got} and gets exactly
what it missed, in order, without the usual welcome burst (so nothing shows twice).
Old clients never send "resume" and work as before (they ignore "seq")."""
import time

import pytest

from chatserver import config, resume, state

pytestmark = pytest.mark.integration


def login_info(client):
    return next(m for m in client.messages if m.get("type") == "auth_result")


def last_seq(client):
    return max(m["seq"] for m in client.messages if "seq" in m)


def come_back(connect, name, token, seq, features=None):
    client = connect()
    packet = {"type": "auth", "action": "resume", "username": name, "token": token, "seq": seq}
    if features is not None:
        packet["features"] = features
    client.send(packet)
    return client, client.expect(lambda m: m.get("type") == "auth_result")


def test_logging_in_gives_a_token_and_packets_have_growing_seq_numbers(user):
    adi = user("Adi")
    adi.line("hello")
    adi.expect(lambda m: m.get("type") == "chat")
    token = login_info(adi)["resume_token"]
    seqs = [m["seq"] for m in adi.messages if "seq" in m]
    assert isinstance(token, str) and len(token) >= 16
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs) and len(seqs) >= 3


def test_a_dropped_client_gets_exactly_what_it_missed(user, connect):
    adi, ben = user("Adi"), user("Ben")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.close()
    ben.expect_text("Adi left the chat")
    ben.line("are you there?")
    ben.line("hello??")
    ben.expect(lambda m: m.get("text") == "hello??")
    back, result = come_back(connect, "Adi", token, seen)
    assert result["ok"] and result["resumed"] is True and result["resume_token"] != token
    missed = back.expect(lambda m: m.get("text") == "hello??")
    texts = [m.get("text") for m in back.messages if m.get("type") == "chat"]
    assert texts == ["are you there?", "hello??"]                     # in order, once each
    assert all(m["seq"] > seen for m in back.messages if "seq" in m)
    assert not [m for m in back.messages if m.get("type") == "history"]   # no welcome burst
    assert missed["seq"] > seen
    ben.expect_text("Adi joined the chat")


def test_nothing_missed_nothing_replayed(user, connect):
    adi = user("Adi")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.close()
    back, result = come_back(connect, "Adi", token, seen)
    assert result["resumed"] is True
    back.line("/users")
    back.expect_text("Online now")
    assert not [m for m in back.messages if m.get("type") == "chat"]


def test_a_wrong_token_is_refused(user, connect):
    adi = user("Adi")
    seen = last_seq(adi)
    adi.close()
    _, result = come_back(connect, "Adi", "not-the-token", seen)
    assert not result["ok"] and "Log in again" in result["text"]


def test_a_token_works_once(user, connect):
    adi = user("Adi")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.close()
    back, _ = come_back(connect, "Adi", token, seen)
    back.close()
    _, again = come_back(connect, "Adi", token, seen)
    assert not again["ok"]


def test_too_old_to_resume_logs_in_normally_with_history(user, connect, monkeypatch):
    monkeypatch.setattr(config, "RESUME_KEEP", 2)          # only the last 2 packets are kept
    adi = user("Adi")
    token = login_info(adi)["resume_token"]
    adi.close()
    back, result = come_back(connect, "Adi", token, 0)     # it wants everything from the start: gone
    assert result["ok"] and result["resumed"] is False
    back.expect(lambda m: m.get("type") == "history")


def test_after_ten_minutes_away_the_token_is_dead(user, connect, monkeypatch):
    adi = user("Adi")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.close()
    user("Ben").line("/users")
    real = time.time
    monkeypatch.setattr(resume.time, "time", lambda: real() + config.RESUME_SECONDS + 1)
    _, result = come_back(connect, "Adi", token, seen)
    assert not result["ok"]


def test_back_in_the_same_room(user, connect):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and m.get("key") == "potatoes")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.close()
    ben.line("in the group")
    ben.expect(lambda m: m.get("text") == "in the group")
    back, _ = come_back(connect, "Adi", token, seen)
    back.expect(lambda m: m.get("text") == "in the group")
    assert state.online["adi"].room == "potatoes"


def test_quitting_on_purpose_ends_the_token(user, connect):
    adi = user("Adi")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.line("/quit")
    ben = user("Ben")
    ben.line("/users")
    ben.expect_text("Online now (1)")                       # Adi is really gone
    _, result = come_back(connect, "Adi", token, seen)
    assert not result["ok"]


def test_live_only_packets_have_no_seq(user):
    adi = user("Adi", features=["typing"])
    ben = user("Ben", features=["typing"])
    ben.send({"type": "typing"})
    typing = adi.expect(lambda m: m.get("type") == "typing")
    assert "seq" not in typing
    adi.send({"type": "ping", "t": 1})
    assert "seq" not in adi.expect(lambda m: m.get("type") == "pong")


def test_old_clients_are_unchanged_apart_from_extra_fields(user):
    old = user("Old")
    result = login_info(old)
    assert result["ok"] and result["text"].startswith("✅")
    assert any(m.get("type") == "history" for m in old.messages)


def test_client_py_reconnects_by_itself_and_catches_up(chat_server, user, monkeypatch):
    """The terminal client: the server drops it, it reconnects with the token and shows what it missed."""
    import socket
    import client as terminal
    from chatserver import session
    sock = socket.create_connection(("127.0.0.1", chat_server))
    monkeypatch.setattr(terminal, "PORT", chat_server)
    monkeypatch.setattr(terminal, "RECONNECT_WAITS", (0.1, 0.2))
    monkeypatch.setattr(terminal, "link", {"sock": sock, "server": "127.0.0.1", "username": "Adi", "token": "",
                                           "seq": 0, "kicked": False})
    terminal.send(sock, {"type": "auth", "action": "register", "username": "Adi", "password": "pass1234",
                         "features": terminal.FEATURES})
    messages = terminal.read_messages(sock)
    for msg in messages:
        terminal.keep(msg)
        if msg.get("type") == "topic":            # the end of the login burst
            break
    ben = user("Ben")
    with state.lock:
        session.hang_up(state.online["adi"])        # the Wi-Fi drops
    ben.expect_text("Adi left the chat")
    ben.line("did you see this?")
    ben.expect(lambda m: m.get("text") == "did you see this?")
    caught_up = terminal.reconnect()
    assert caught_up is not None
    for msg in caught_up:
        if terminal.keep(msg) and msg.get("text") == "did you see this?":
            break
    assert terminal.link["sock"] is not sock and "adi" in state.online
    terminal.link["sock"].close()
