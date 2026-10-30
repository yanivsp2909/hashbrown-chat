"""Bug fixes: stuck logins (D4 takeover), password guessing (per-username lockout), /admin (D5)."""
import time

import pytest

from chatserver import config, connections, state
from chatserver import auth as server_auth   # 'auth' is already helpers.auth (logs a fake client in)
from helpers import auth
from test_smoke import start_game

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------- D4: logging in again takes over

def test_logging_in_again_replaces_the_old_session(connect, user):
    old = user("Adi")
    new = connect()
    result = auth(new, "login", "Adi", "pass1234")
    assert result["ok"]
    assert result["text"] == "✅ Welcome back, Adi!"  # the website matches this exact text
    note = old.expect_text("another window", kind="error")
    assert "already logged in somewhere else" not in note["text"]  # would confuse the website
    assert old.wait_closed()
    new.sync()
    assert state.online["adi"] is not None


def test_old_session_cannot_act_after_being_replaced(connect, user):
    old, ben = user("Adi"), user("Ben")
    new = connect()
    assert auth(new, "login", "Adi", "pass1234")["ok"]
    old.wait_closed()
    try:
        old.line("/give Ben 50")
    except OSError:
        pass
    new.sync()
    assert state.accounts["ben"]["tokens"] == config.START_TOKENS


def test_wrong_password_does_not_replace_the_session(connect, user):
    old = user("Adi")
    result = auth(connect(), "login", "Adi", "wrong-pass")
    assert not result["ok"]
    old.sync()  # still connected and working


def test_taking_over_keeps_your_game_going(connect, user):
    adi, ben = user("Adi"), user("Ben")
    start_game(adi, ben, "ttt")
    new = connect()
    assert auth(new, "login", "Adi", "pass1234")["ok"]
    adi.wait_closed()
    new.line("/board")
    new.expect_board()
    assert state.matches.get("ben") is state.matches.get("adi") is not None
    assert not any("YOU WON" in t for t in ben.texts())


# ---------------------------------------------------------------- password guessing

def wrong_logins(connect, name, times):
    for _ in range(times):  # a new connection each time, like an attacker would
        client = connect()
        assert not auth(client, "login", name, "wrong-pass")["ok"]
        client.close()


def test_account_locks_after_five_wrong_passwords_from_many_connections(connect, user):
    adi = user("Adi")
    adi.line("/quit")
    adi.wait_closed()
    wrong_logins(connect, "Adi", 5)
    result = auth(connect(), "login", "Adi", "pass1234")
    assert not result["ok"]
    assert "🔒" in result["text"]


def test_lockout_is_per_username_not_for_everyone(connect, user):
    adi, ben = user("Adi"), user("Ben")
    for client in (adi, ben):
        client.line("/quit")
        client.wait_closed()
    wrong_logins(connect, "Adi", 5)
    assert auth(connect(), "login", "Ben", "pass1234")["ok"]  # same IP, different account: fine


def test_lockout_ends_after_a_while(connect, user, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_LOCK_SECONDS", 0.5)
    adi = user("Adi")
    adi.line("/quit")
    adi.wait_closed()
    wrong_logins(connect, "Adi", 5)
    time.sleep(0.6)
    assert auth(connect(), "login", "Adi", "pass1234")["ok"]


def test_unknown_usernames_take_as_long_as_real_ones(connect, monkeypatch):
    hashed = []
    real = server_auth.hash_password
    monkeypatch.setattr(server_auth, "hash_password", lambda *a: (hashed.append(1), real(*a))[1])
    assert not auth(connect(), "login", "Nobody", "pass1234")["ok"]
    assert hashed  # a dummy hash ran, so timing doesn't reveal who has an account


# ---------------------------------------------------------------- D5: /admin

def test_no_password_in_the_code_so_admin_is_off_without_the_environment(user):
    """The repo is public: the password only comes from HASHBROWN_ADMIN_PASSWORD (start.sh reads it from the
    Keychain). Without it /admin is off, and the old built-in "123" doesn't work."""
    assert not hasattr(config, "ADMIN_PASSWORD")
    adi = user("Adi")
    adi.line("/admin 123")
    adi.expect_text("disabled", kind="error")
    assert not state.accounts["adi"]["admin"]


def test_a_short_password_works_too(user, monkeypatch):
    monkeypatch.setenv("HASHBROWN_ADMIN_PASSWORD", "abc")
    adi = user("Adi")
    adi.line("/admin abc")
    adi.expect_text("You're now an admin", kind="event")


def test_admin_password_can_come_from_the_environment(user, monkeypatch):
    monkeypatch.setenv("HASHBROWN_ADMIN_PASSWORD", "long-test-password")
    adi = user("Adi")
    adi.line("/admin long-test-password")
    adi.expect_text("You're now an admin", kind="event")
    assert state.accounts["adi"]["admin"]


def test_admin_lockout_counts_wrong_guesses_from_all_accounts(user, monkeypatch):
    monkeypatch.setenv("HASHBROWN_ADMIN_PASSWORD", "long-test-password")
    adi, ben, cara = user("Adi"), user("Ben"), user("Cara")
    for guesser in (adi, ben, cara):
        guesser.line("/admin guess")
        guesser.expect_text("Wrong admin password", kind="error")
    dan = user("Dan")
    dan.line("/admin long-test-password")
    dan.expect_text("Too many wrong", kind="error")
    assert not state.accounts["dan"]["admin"]


def startup_output(capsys):
    listener = connections.start_server("127.0.0.1", 0, run_loops=False, run_console=False)
    listener.close()
    return capsys.readouterr().out


@pytest.mark.parametrize("password", ["long-test-password", "abc12"])
def test_startup_never_prints_the_admin_password(monkeypatch, capsys, password):
    monkeypatch.setenv("HASHBROWN_ADMIN_PASSWORD", password)
    assert password not in startup_output(capsys)


def test_a_short_password_gets_one_warning_line_at_startup(monkeypatch, capsys):
    monkeypatch.setenv("HASHBROWN_ADMIN_PASSWORD", "abc12")
    out = startup_output(capsys)
    assert len([line for line in out.splitlines() if "shorter than 8" in line]) == 1 and "abc12" not in out
    monkeypatch.setenv("HASHBROWN_ADMIN_PASSWORD", "long-test-password")
    assert "shorter than 8" not in startup_output(capsys)


def test_startup_says_how_to_turn_admin_on_when_there_is_no_password(capsys):
    out = startup_output(capsys)
    assert "HASHBROWN_ADMIN_PASSWORD" in out and "hashbrown-admin" in out


def test_taking_over_tells_your_old_group_that_you_left(connect, user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and "Potatoes" in m["room"])
    assert auth(connect(), "login", "Adi", "pass1234")["ok"]
    ben.expect_text("Adi left")
