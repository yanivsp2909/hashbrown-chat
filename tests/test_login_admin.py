"""Bug fixes: stuck logins (D4 takeover), password guessing (per-username lockout), /admin (D5)."""
import time

import pytest

import server
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
    assert server.online["adi"] is not None


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
    assert server.accounts["ben"]["tokens"] == server.START_TOKENS


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
    assert server.matches.get("ben") is server.matches.get("adi") is not None
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
    monkeypatch.setattr(server, "LOGIN_LOCK_SECONDS", 0.5)
    adi = user("Adi")
    adi.line("/quit")
    adi.wait_closed()
    wrong_logins(connect, "Adi", 5)
    time.sleep(0.6)
    assert auth(connect(), "login", "Adi", "pass1234")["ok"]


def test_unknown_usernames_take_as_long_as_real_ones(connect, monkeypatch):
    hashed = []
    real = server.hash_password
    monkeypatch.setattr(server, "hash_password", lambda *a: (hashed.append(1), real(*a))[1])
    assert not auth(connect(), "login", "Nobody", "pass1234")["ok"]
    assert hashed  # a dummy hash ran, so timing doesn't reveal who has an account


# ---------------------------------------------------------------- D5: /admin

def test_admin_works_with_the_password_at_the_top(user):
    adi = user("Adi")
    adi.line("/admin 123")
    adi.expect_text("You're now an admin", kind="event")
    assert server.accounts["adi"]["admin"]


def test_admin_is_disabled_while_the_password_is_empty(user, monkeypatch):
    monkeypatch.setattr(server, "ADMIN_PASSWORD", "")
    adi = user("Adi")
    adi.line("/admin ")
    adi.expect_text("disabled", kind="error")
    assert not server.accounts["adi"]["admin"]


def test_admin_password_can_come_from_the_environment(user, monkeypatch):
    monkeypatch.setenv("HASHBROWN_ADMIN_PASSWORD", "long-test-password")
    adi = user("Adi")
    adi.line("/admin long-test-password")
    adi.expect_text("You're now an admin", kind="event")
    assert server.accounts["adi"]["admin"]


def test_admin_lockout_counts_wrong_guesses_from_all_accounts(user, monkeypatch):
    monkeypatch.setenv("HASHBROWN_ADMIN_PASSWORD", "long-test-password")
    adi, ben, cara = user("Adi"), user("Ben"), user("Cara")
    for guesser in (adi, ben, cara):
        guesser.line("/admin guess")
        guesser.expect_text("Wrong admin password", kind="error")
    dan = user("Dan")
    dan.line("/admin long-test-password")
    dan.expect_text("Too many wrong", kind="error")
    assert not server.accounts["dan"]["admin"]


def startup_output(capsys):
    listener = server.start_server("127.0.0.1", 0, run_loops=False, run_console=False)
    listener.close()
    return capsys.readouterr().out


@pytest.mark.parametrize("password", [None, "long-test-password"])
def test_startup_never_prints_the_admin_password(monkeypatch, capsys, password):
    if password:
        monkeypatch.setenv("HASHBROWN_ADMIN_PASSWORD", password)
    secret = password or server.ADMIN_PASSWORD
    assert secret not in startup_output(capsys)


def test_startup_says_how_to_turn_admin_on_when_the_password_is_empty(monkeypatch, capsys):
    monkeypatch.setattr(server, "ADMIN_PASSWORD", "")
    assert "HASHBROWN_ADMIN_PASSWORD" in startup_output(capsys)


def test_taking_over_tells_your_old_group_that_you_left(connect, user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and "Potatoes" in m["room"])
    assert auth(connect(), "login", "Adi", "pass1234")["ok"]
    ben.expect_text("Adi left")
