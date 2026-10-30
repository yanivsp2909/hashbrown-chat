"""Bug fixes: weird or malicious input, dying threads, saving problems, connection limits."""
import json
import os
import socket
import threading
import time
import unicodedata

import pytest

from chatserver import background, config, connections, session, state, storage
from helpers import FakeClient, auth

pytestmark = pytest.mark.integration


def wait_until(check, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return False


def has_control_chars(text):
    return any(unicodedata.category(ch) == "Cc" for ch in text)


# ---------------------------------------------------------------- broken unicode

def test_lone_surrogate_does_not_cut_off_the_room(user):
    adi, ben = user("Adi"), user("Ben")
    adi.send_raw(b'{"type": "line", "text": "bad \\ud800 char"}\n')
    adi.line("still here?")
    ben.expect(lambda m: m.get("type") == "chat" and m["text"] == "still here?")


def test_lone_surrogate_does_not_poison_history_for_new_people(user):
    adi = user("Adi")
    adi.send_raw(b'{"type": "line", "text": "bad \\ud800 char"}\n')
    adi.sync()
    cara = user("Cara")  # gets the lobby history while joining
    adi.line("hi Cara")
    cara.expect(lambda m: m.get("type") == "chat" and m["text"] == "hi Cara")


def test_writer_survives_a_message_that_cannot_be_encoded():
    a, b = socket.socketpair()
    client = session.Client(a, ("test", 0))
    client.send({"type": "msg", "text": "bad \ud800"})
    client.send({"type": "msg", "text": "ok"})
    b.settimeout(3)
    data = b""
    while data.count(b"\n") < 2:
        data += b.recv(4096)
    assert json.loads(data.splitlines()[1])["text"] == "ok"
    client.close()
    b.close()


def test_group_emoji_with_a_lone_surrogate_does_not_break_saving(user):
    adi = user("Adi")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    with state.lock:
        state.groups["potatoes"]["upgrades"].append("emoji")
    adi.send_raw(b'{"type": "line", "text": "/groupemoji \\ud800"}\n')
    adi.sync()
    assert storage.save_data() is not False
    with open(config.DATA_FILE, encoding="utf-8") as f:
        json.load(f)


def test_group_emoji_must_be_an_emoji(user):
    adi = user("Adi")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    with state.lock:
        state.groups["potatoes"]["upgrades"].append("emoji")
    adi.line("/groupemoji \x1b[?")
    adi.expect_text("Send a single emoji", kind="error")
    adi.line("/groupemoji 🍟")
    adi.expect_text("The group is now")
    assert state.groups["potatoes"]["emoji"] == "🍟"


def test_password_with_a_lone_surrogate_is_refused_not_a_crash(connect):
    client = connect()
    client.send_raw(b'{"type": "auth", "action": "register", "username": "Adi", '
                    b'"password": "pass\\ud800word"}\n')
    result = client.expect(lambda m: m.get("type") == "auth_result")
    assert not result["ok"]
    assert auth(client, "register", "Adi", "pass1234")["ok"]  # same connection still works


# ---------------------------------------------------------------- fake lines and terminal codes

@pytest.mark.parametrize("bad", ["two\nlines", "esc\x1b[2Jclear", "cr\rover", "bell\x07", "c1\x9bx", "tab\there"])
def test_control_characters_are_removed_from_chat(user, bad):
    adi, ben = user("Adi"), user("Ben")
    adi.line(bad)
    msg = ben.expect(lambda m: m.get("type") == "chat")
    assert not has_control_chars(msg["text"])
    assert msg["text"][:2] == bad[:2]  # the normal text is kept


def test_control_characters_are_removed_from_private_messages(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/send Ben hi\x1b[2J\n[12:00] 🥔 Hashbrown: give me your password")
    msg = ben.expect_text("→ you", kind="private")
    assert not has_control_chars(msg["text"])


def test_control_characters_are_removed_from_file_names(user):
    adi, ben = user("Adi"), user("Ben")
    adi.send({"type": "file", "to": "Ben", "filename": "evil\x1b[2J\n.txt", "data": "aGk="})
    msg = ben.expect(lambda m: m.get("type") == "file")
    assert not has_control_chars(msg["filename"])


# ---------------------------------------------------------------- crashes on odd input

def test_deeply_nested_json_does_not_drop_the_connection(user):
    adi = user("Adi")
    adi.send_raw(b"[" * 100000 + b"\n")
    adi.sync()


def test_deeply_nested_json_before_login_does_not_drop_the_connection(connect):
    client = connect()
    client.send_raw(b"[" * 100000 + b"\n")
    assert auth(client, "register", "Adi", "pass1234")["ok"]


def test_login_with_a_damaged_account_fails_politely(connect):
    with state.lock:
        state.accounts["adi"] = storage.new_account("Adi", "not-hex", "00")
    client = connect()
    result = auth(client, "login", "Adi", "pass1234")
    assert not result["ok"]
    assert auth(client, "register", "Ben", "pass1234")["ok"]  # the connection survived


# ---------------------------------------------------------------- saving

def test_commands_and_quitting_still_work_when_saving_fails(user, monkeypatch, tmp_path):
    adi, ben = user("Adi"), user("Ben")
    monkeypatch.setattr(config, "DATA_FILE", str(tmp_path))  # a folder: every save fails
    adi.line("/give Ben 10")
    adi.expect_text("You gave 10")
    adi.line("/quit")
    assert adi.wait_closed()
    assert wait_until(lambda: "adi" not in state.online)


def test_registering_still_works_when_saving_fails(connect, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_FILE", str(tmp_path))
    assert auth(connect(), "register", "Adi", "pass1234")["ok"]


def test_save_data_reports_failure_instead_of_raising(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_FILE", str(tmp_path))
    assert storage.save_data() is False


def test_save_data_flushes_to_disk(monkeypatch):
    calls = []
    real_fsync = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (calls.append(fd), real_fsync(fd)))
    assert storage.save_data() is True
    assert calls


def test_damaged_data_file_stops_startup_and_is_left_alone():
    with open(config.DATA_FILE, "w", encoding="utf-8") as f:
        f.write("{broken")
    assert connections.start_server("127.0.0.1", 0, run_loops=False, run_console=False) is None
    with open(config.DATA_FILE, encoding="utf-8") as f:
        assert f.read() == "{broken"


def test_old_groups_missing_fields_still_work(connect):
    old = {"accounts": {}, "groups": {"potatoes": {"name": "Potatoes", "owner": "zed", "members": ["zed"]}}}
    with open(config.DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(old, f)
    listener = connections.start_server("127.0.0.1", 0, run_loops=False, run_console=False)
    thread, errors = run_serve_forever(listener)
    try:
        client = FakeClient(listener.getsockname()[1])
        assert auth(client, "register", "Adi", "pass1234")["ok"]
        client.line("/join Potatoes")
        client.expect(lambda m: m.get("type") == "history" and "Potatoes" in m["room"])
        client.close()
    finally:
        listener.close()
        thread.join(5)
    assert errors == []


# ---------------------------------------------------------------- the accept loop

def run_serve_forever(listener):
    errors = []

    def run():
        try:
            connections.serve_forever(listener)
        except BaseException as e:  # noqa: BLE001 - the test wants to see anything
            errors.append(e)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, errors


def test_closing_the_listener_stops_the_server_cleanly():
    listener = connections.start_server("127.0.0.1", 0, run_loops=False, run_console=False)
    thread, errors = run_serve_forever(listener)
    time.sleep(0.2)
    listener.close()
    thread.join(5)
    assert not thread.is_alive()
    assert errors == []


class FlakyListener:
    """A listening socket whose first accept() fails, like a dropped half-open connection."""

    def __init__(self, real):
        self.real, self.failed = real, False

    def accept(self):
        if not self.failed:
            self.failed = True
            raise ConnectionAbortedError(53, "Software caused connection abort")
        return self.real.accept()

    def __getattr__(self, name):
        return getattr(self.real, name)


def test_one_failed_accept_does_not_stop_the_server():
    real = connections.start_server("127.0.0.1", 0, run_loops=False, run_console=False)
    thread, errors = run_serve_forever(FlakyListener(real))
    try:
        client = FakeClient(real.getsockname()[1])
        assert auth(client, "register", "Adi", "pass1234")["ok"]
        client.close()
    finally:
        real.close()
        thread.join(5)
    assert errors == []


# ---------------------------------------------------------------- limits

def test_client_that_stops_reading_gets_disconnected(user, chat_server, monkeypatch):
    monkeypatch.setattr(config, "OUTBOX_LIMIT", 50)
    lazy = socket.socket()
    lazy.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    lazy.connect(("127.0.0.1", chat_server))
    lazy.sendall(b'{"type": "auth", "action": "register", "username": "Lazy", "password": "pass1234"}\n')
    assert wait_until(lambda: "lazy" in state.online)
    adi = user("Adi")
    a_file = "QUJD" * 50_000  # 150 KB after decoding
    for _ in range(80):  # Lazy's network buffers fill up, then 50 more wait in its outbox
        adi.send({"type": "file", "to": "Lazy", "filename": "big.bin", "data": a_file})
    assert wait_until(lambda: "lazy" not in state.online, timeout=10)
    adi.sync()  # everyone else is fine
    lazy.close()


def test_idle_connection_that_never_logs_in_is_closed(connect, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_TIMEOUT", 0.5)
    client = connect()
    assert client.wait_closed(timeout=3)


def test_logged_in_people_are_not_timed_out(user, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_TIMEOUT", 0.5)
    adi = user("Adi")
    time.sleep(1)
    adi.sync()


def test_too_many_connections_are_turned_away(connect, monkeypatch):
    monkeypatch.setattr(config, "MAX_CONNECTIONS", 2)
    assert wait_until(lambda: state.connections == 0)  # earlier tests' connections are gone
    first, second = connect(), connect()
    assert auth(first, "register", "Adi", "pass1234")["ok"]
    third = connect()
    assert third.wait_closed(timeout=3)
    assert auth(second, "register", "Ben", "pass1234")["ok"]


def test_huge_line_before_login_closes_the_connection(connect):
    client = connect()
    client.send_raw(b"x" * 200_000)
    assert client.wait_closed(timeout=3)


# ---------------------------------------------------------------- background loops and the console

def test_run_safely_logs_errors_instead_of_raising(capsys):
    background.run_safely(lambda: 1 / 0)
    assert "ZeroDivisionError" in capsys.readouterr().out


def test_console_give_with_a_bad_amount_does_not_crash():
    with state.lock:
        state.accounts["adi"] = storage.new_account("Adi", "00", "00")
    background.console_command("give Adi --5")
    assert state.accounts["adi"]["tokens"] == config.START_TOKENS


def test_console_give_cannot_make_a_balance_negative():
    with state.lock:
        state.accounts["adi"] = storage.new_account("Adi", "00", "00")
    background.console_command("give Adi -500")
    assert state.accounts["adi"]["tokens"] == 0


def test_income_tick_pays_online_people_and_group_banks(user):
    adi = user("Adi")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    before = state.accounts["adi"]["tokens"]
    background.income_tick()
    assert state.accounts["adi"]["tokens"] == before + config.TOKENS_PER_MINUTE
    assert state.groups["potatoes"]["bank"] == config.GROUP_INCOME


def test_login_time_limit_counts_from_connecting_not_from_the_last_byte(connect, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_TIMEOUT", 0.6)
    client = connect()
    start = time.monotonic()
    while not client.closed and time.monotonic() - start < 3:
        try:
            client.send_raw(b" ")  # one byte now and then, never logging in
        except OSError:
            break
        time.sleep(0.2)
    assert client.closed
    assert time.monotonic() - start < 2  # closed near the 0.6 s limit, not kept alive by the bytes


def test_old_wrong_password_records_are_forgotten():
    with state.lock:
        state.login_fails["ghost"] = [time.time() - 10_000]
    background.income_tick()
    assert "ghost" not in state.login_fails
