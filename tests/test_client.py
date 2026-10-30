"""Unit tests for client.py (no real server, no real terminal)."""
import base64
import os
import socket
import sys
import threading
import types

import pytest

import client

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def quiet_console(monkeypatch):
    monkeypatch.setattr(client.console, "smart", False)  # plain print(), like the PyCharm run window
    client.quitting.clear()
    yield
    client.quitting.clear()


class FakeSock:
    """recv() hands out the items one by one: bytes, or an exception to raise."""

    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.sent = []

    def recv(self, size):
        item = self.chunks.pop(0) if self.chunks else b""
        if isinstance(item, Exception):
            raise item
        return item

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, value):
        pass


# ---------------------------------------------------------------- C1: terminal escape injection

def test_printable_strips_controls_but_keeps_text():
    assert client.printable("a\x1b[2Jb\rc\x07d\x9be\x7f") == "a[2Jbcde"
    assert client.printable("line1\nline2") == "line1\nline2"
    assert client.printable("שלום 😀 café") == "שלום 😀 café"


def test_printable_turns_tab_into_space():
    assert client.printable("a\tb") == "a b"


def test_show_msg_strips_escape_codes(capsys):
    client.show({"type": "msg", "text": "hi\x1b[2J\rforged"})
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\r" not in out
    assert "hi" in out and "forged" in out


def test_show_chat_strips_escape_codes_from_every_field(capsys):
    client.show({"type": "chat", "name": "ev\x1b[2Jil", "badge": "\x9b[x", "text": "a\x1b]0;title\x07b",
                 "time": "10:\x1b00"})
    out = capsys.readouterr().out
    assert "\x1b[2J" not in out and "\x1b]" not in out and "\x9b" not in out and "\x07" not in out
    assert "\x1b00" not in out


def test_show_history_strips_escape_codes(capsys):
    client.show({"type": "history", "room": "lobby\x1b[2J",
                 "messages": [{"name": "x", "text": "t\x1b[H", "time": "1"}]})
    out = capsys.readouterr().out
    assert "\x1b[2J" not in out and "\x1b[H" not in out and "lobby" in out


def test_save_file_message_strips_escape_codes(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(client, "DOWNLOAD_DIR", str(tmp_path / "dl"))
    client.show({"type": "file", "from": "me\x1b[2J", "filename": "a\x1b[2J.txt",
                 "data": base64.b64encode(b"hello").decode()})
    out = capsys.readouterr().out
    assert "\x1b[2J" not in out and "saved to" in out


# ---------------------------------------------------------------- C2: RecursionError

def test_read_messages_survives_deeply_nested_json():
    deep = b"[" * 100000 + b"\n"
    good = b'{"type": "msg", "text": "still alive"}\n'
    got = list(client.read_messages(FakeSock([deep + good, b""])))
    assert got == [{"type": "msg", "text": "still alive"}]


# ---------------------------------------------------------------- C3: one bad message never kills the receiver

def test_show_survives_history_with_non_dicts(capsys):
    client.show({"type": "history", "room": "lobby", "messages": [1, "a", None]})
    assert "⚠️" in capsys.readouterr().out


def test_receive_loop_keeps_going_after_a_bad_message(capsys):
    client.quitting.set()  # so the loop doesn't print the "disconnected" line
    bad = {"type": "history", "room": "r", "messages": [5]}
    good = {"type": "msg", "text": "after the bad one"}
    client.receive_loop(iter([bad, good]))
    assert "after the bad one" in capsys.readouterr().out


def test_save_file_reports_an_unwritable_folder(capsys, tmp_path, monkeypatch):
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("x")
    monkeypatch.setattr(client, "DOWNLOAD_DIR", str(blocker))  # makedirs fails on it
    client.save_file({"from": "bob", "filename": "a.txt", "data": base64.b64encode(b"hi").decode()})
    out = capsys.readouterr().out
    assert "bob" in out and "couldn't save" in out


def test_save_file_reports_a_write_error(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(client, "DOWNLOAD_DIR", str(tmp_path))

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", boom)
    client.save_file({"from": "bob", "filename": "a.txt", "data": base64.b64encode(b"hi").decode()})
    monkeypatch.undo()
    assert "couldn't save" in capsys.readouterr().out


def test_save_file_normal_case_still_works(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(client, "DOWNLOAD_DIR", str(tmp_path / "dl"))
    client.save_file({"from": "bob", "filename": "a.txt", "data": base64.b64encode(b"hi").decode()})
    assert (tmp_path / "dl" / "a.txt").read_bytes() == b"hi"
    assert "saved to" in capsys.readouterr().out


# ---------------------------------------------------------------- C4: unreadable file

@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="needs a normal user on a POSIX system")
def test_send_file_unreadable_file_prints_an_error(capsys, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("nope")
    secret.chmod(0)
    sock = FakeSock()
    try:
        client.send_file(sock, f"/sendfile bob {secret}")
    finally:
        secret.chmod(0o600)
    assert sock.sent == []
    assert "Can't read" in capsys.readouterr().out


def test_send_file_sends_a_normal_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hi")
    sock = FakeSock()
    client.send_file(sock, f"/sendfile bob {f}")
    assert len(sock.sent) == 1 and b'"type": "file"' in sock.sent[0]


# ---------------------------------------------------------------- C5: Mac/Linux raw keys

class KeyPipe:
    """A pipe standing in for the keyboard. The writer stays open, like a real terminal."""

    def __init__(self):
        self.read_fd, self.write_fd = os.pipe()
        self.keys = client.InputLine()._read_unix_keys(self.read_fd)

    def type(self, data):
        os.write(self.write_fd, data)

    def next_key(self, timeout=2):
        """Next key, or fail if the generator is stuck waiting for more input."""
        box = []

        def work():
            try:
                box.append(next(self.keys))
            except BaseException as e:  # shown in the failure instead of vanishing in a thread
                box.append(e)

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            os.write(self.write_fd, b"\n")  # let the stuck thread finish so it doesn't linger
            pytest.fail("the key reader is stuck waiting for more input")
        if isinstance(box[0], BaseException):
            raise box[0]
        return box[0]

    def keys_until(self, last):
        out = []
        while not out or out[-1] != last:
            out.append(self.next_key())
        return [k for k in out if k != "ignore"]

    def close(self):
        os.close(self.read_fd)
        os.close(self.write_fd)


@pytest.fixture
def pipe():
    p = KeyPipe()
    yield p
    p.close()


def test_unix_plain_letters_and_enter(pipe):
    pipe.type("hi שלום\r".encode())
    assert pipe.keys_until("enter") == list("hi שלום") + ["enter"]


def test_unix_lone_escape_is_not_swallowed(pipe):
    pipe.type(b"\x1b")
    assert pipe.next_key() == "escape"
    pipe.type(b"a")
    assert pipe.next_key() == "a"


def test_unix_arrows(pipe):
    pipe.type(b"\x1b[A\x1b[Ba")
    assert pipe.keys_until("a") == ["up", "down", "a"]


def test_unix_application_mode_arrows_type_nothing(pipe):
    pipe.type(b"\x1bOA\x1bOBa")
    assert pipe.keys_until("a") == ["up", "down", "a"]


@pytest.mark.parametrize("sequence", [b"\x1b[3~", b"\x1b[H", b"\x1b[F", b"\x1b[5~", b"\x1b[6~",
                                      b"\x1b[1~", b"\x1b[4~", b"\x1b[C", b"\x1b[D", b"\x1bOH", b"\x1bOP"])
def test_unix_other_special_keys_leave_no_stray_characters(pipe, sequence):
    pipe.type(sequence + b"a")
    assert pipe.keys_until("a") == ["a"]


def test_unix_arrow_with_modifier_parameters(pipe):
    pipe.type(b"\x1b[1;5Aa")
    assert pipe.keys_until("a") == ["up", "a"]


def test_unix_escape_then_normal_key_keeps_the_key(pipe):
    pipe.type(b"\x1bx")
    assert pipe.keys_until("x") == ["escape", "x"]


def test_unix_end_of_input_raises_eof(pipe):
    os.close(pipe.write_fd)
    pipe.write_fd = os.open(os.devnull, os.O_WRONLY)  # so close() in the fixture still works
    with pytest.raises(EOFError):
        next(pipe.keys)


# ---------------------------------------------------------------- C6: Windows keys

def fake_msvcrt(monkeypatch, typed):
    queue = list(typed)
    module = types.ModuleType("msvcrt")
    module.getwch = lambda: queue.pop(0)
    monkeypatch.setitem(sys.modules, "msvcrt", module)


def windows_keys_until_enter():
    keys = []
    for key in client.InputLine._windows_keys():
        keys.append(key)
        if key == "enter":
            return keys


def test_windows_valid_emoji_pair(monkeypatch):
    fake_msvcrt(monkeypatch, ["\ud83d", "\ude00", "\r"])
    assert windows_keys_until_enter() == ["😀", "enter"]


def test_windows_malformed_surrogate_pair_is_ignored(monkeypatch):
    fake_msvcrt(monkeypatch, ["\ud800", "a", "b", "\r"])
    keys = windows_keys_until_enter()
    assert keys[-2:] == ["b", "enter"]
    assert not any("\ud800" in k for k in keys)


def test_windows_arrows(monkeypatch):
    fake_msvcrt(monkeypatch, ["\xe0", "H", "\x00", "P", "\r"])
    assert windows_keys_until_enter() == ["up", "down", "enter"]


# ---------------------------------------------------------------- C7: login when the connection closes

def run_login(monkeypatch, sock, capsys):
    answers = iter(["1", "bob"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(client, "ask_password", lambda prompt="Password: ": "pw")
    result = client.login(sock, client.read_messages(sock))
    return result, capsys.readouterr().out


def test_login_says_server_closed_the_connection(monkeypatch, capsys):
    kicked = b'{"type": "msg", "kind": "error", "text": "\\ud83d\\udeab Too many failed attempts. Bye."}\n'
    result, out = run_login(monkeypatch, FakeSock([kicked, b""]), capsys)
    assert result is False
    assert "Too many failed attempts" in out
    assert "closed the connection" in out
    assert "No answer from the server" not in out


def test_login_timeout_still_says_no_answer(monkeypatch, capsys):
    result, out = run_login(monkeypatch, FakeSock([socket.timeout("timed out")]), capsys)
    assert result is False
    assert "No answer from the server" in out
    assert "closed the connection" not in out


def test_login_success(monkeypatch, capsys):
    ok = b'{"type": "auth_result", "ok": true, "text": "Welcome bob"}\n'
    result, out = run_login(monkeypatch, FakeSock([ok]), capsys)
    assert result is True and "Welcome bob" in out


# ---------------------------------------------------------------- C8: /sendfile prefix

def run_chat_loop(monkeypatch, lines):
    sock = FakeSock()
    typed = iter(lines)
    monkeypatch.setattr(client.console, "read", lambda: next(typed))
    calls = []
    monkeypatch.setattr(client, "send_file", lambda s, line: calls.append(line))
    client.chat_loop(sock)
    return calls, sock.sent


def test_sendfilex_is_a_normal_chat_line(monkeypatch):
    calls, sent = run_chat_loop(monkeypatch, ["/sendfilex hello there", "/quit"])
    assert calls == []
    assert b"/sendfilex hello there" in sent[0]


@pytest.mark.parametrize("line", ["/sendfile", "/sendfile bob a.txt", "/SENDFILE bob a.txt"])
def test_sendfile_commands_go_to_send_file(monkeypatch, line):
    calls, sent = run_chat_loop(monkeypatch, [line, "/quit"])
    assert calls == [line]
    assert len(sent) == 1  # only the /quit line went to the server


# ---------------------------------------------------------------- 🌐 terminal or website?

def test_the_ip_is_the_first_argument_that_isnt_a_flag():
    assert client.parse_args([]) == ("127.0.0.1", set())
    assert client.parse_args(["192.168.1.20"]) == ("192.168.1.20", set())
    assert client.parse_args(["--web", "192.168.1.20"]) == ("192.168.1.20", {"--web"})


def test_enter_picks_the_terminal_and_2_picks_the_website(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    answers = iter(["", "2", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert [client.ask_terminal_or_web() for _ in range(3)] == ["terminal", "web", "terminal"]


def test_no_question_when_the_input_is_not_a_keyboard(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("asked a question"))
    assert client.ask_terminal_or_web() == "terminal"


def test_opening_the_website_checks_it_is_running_first(monkeypatch):
    opened = []
    monkeypatch.setattr(client.webbrowser, "open", opened.append)
    with socket.socket() as website:
        website.bind(("127.0.0.1", 0))
        website.listen()
        monkeypatch.setattr(client, "WEB_PORT", website.getsockname()[1])
        assert client.open_website("127.0.0.1") is True
    assert opened == [f"http://127.0.0.1:{client.WEB_PORT}"]


def test_a_website_that_isnt_running_falls_back_to_the_terminal(monkeypatch, capsys):
    monkeypatch.setattr(client.webbrowser, "open", lambda url: pytest.fail("opened a dead link"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        monkeypatch.setattr(client, "WEB_PORT", s.getsockname()[1])  # nothing listens there
    assert client.open_website("127.0.0.1") is False
    assert "isn't running" in capsys.readouterr().out


# ---------------------------------------------------------------- 🔬 --packets

def test_packets_flag_prints_raw_chunks_and_each_packet(monkeypatch):
    printed = []
    monkeypatch.setattr(client, "FLAGS", {"--packets"})
    monkeypatch.setattr(client.console, "out", printed.append)
    a, b = socket.socketpair()
    b.sendall(b'{"type": "msg", "text": "one"}\n{"type": "msg", "te')
    b.close()
    assert [m["text"] for m in client.read_messages(a)] == ["one"]
    text = "\n".join(printed)
    assert "recv() 50 bytes: 1 packet + the start of one more" in text
    assert '⬇ {"type": "msg", "text": "one"}' in text


def test_packets_flag_shows_what_we_send_but_never_the_password(monkeypatch):
    printed = []
    monkeypatch.setattr(client, "FLAGS", {"--packets"})
    monkeypatch.setattr(client.console, "out", printed.append)
    a, b = socket.socketpair()
    client.send(a, {"type": "auth", "action": "login", "username": "Adi", "password": "secret123"})
    client.send(a, {"type": "line", "text": "hi"})
    text = "\n".join(printed)
    assert "secret123" not in text and '"password": "•••"' in text
    assert '⬆ {"type": "line", "text": "hi"}' in text
    a.close(), b.close()


def test_no_packet_printing_without_the_flag(monkeypatch):
    printed = []
    monkeypatch.setattr(client, "FLAGS", set())
    monkeypatch.setattr(client.console, "out", printed.append)
    a, b = socket.socketpair()
    client.send(a, {"type": "line", "text": "hi"})
    assert printed == []
    a.close(), b.close()
