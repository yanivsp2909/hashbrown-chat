"""🔤 Look-alike names: new usernames (and /nick, and new groups) may only use English letters, Hebrew letters,
digits 0-9 and _, and one alphabet per name, so nobody can pose as "Adi" with a Cyrillic "А".
Existing accounts keep their names and still log in."""
import pytest

from chatserver import auth, rooms, state, storage

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("name", ["Adi", "adi_99", "יניב", "דנה_2", "___", "a1b2c3"])
def test_good_names(name):
    assert rooms.valid_name(name)


@pytest.mark.parametrize("name", [
    "Аdi",          # Cyrillic А + Latin
    "Adiא",         # Latin + Hebrew
    "Ádi",          # an accent
    "Adi١",         # an Arabic-Indic digit
    "Ａdi",         # a fullwidth letter
    "Ελλη",         # Greek
    "ab",           # too short
    "a" * 17,       # too long
    "a-b",
    "hashbrown",    # reserved
])
def test_look_alikes_and_other_alphabets_are_refused(name):
    assert not rooms.valid_name(name)


def register(connect, name):
    client = connect()
    client.send({"type": "auth", "action": "register", "username": name, "password": "pass1234"})
    return client.expect(lambda m: m.get("type") == "auth_result")


def test_registering_a_mixed_name_says_why(connect):
    result = register(connect, "Аdi")
    assert not result["ok"] and "English or Hebrew" in result["text"]


def test_nick_follows_the_same_rule(user):
    adi = user("Adi")
    adi.line("/nick Аdi")
    adi.expect_text("English or Hebrew", kind="error")
    adi.line("/nick אדי")
    adi.expect_text("You still log in as")


def test_an_old_account_with_an_old_style_name_still_logs_in(connect):
    salt, digest = auth.hash_password("pass1234")
    state.accounts["józef"] = {**storage.new_account("Józef", salt, digest), "created": 0}
    client = connect()
    client.send({"type": "auth", "action": "login", "username": "Józef", "password": "pass1234"})
    assert client.expect(lambda m: m.get("type") == "auth_result")["ok"]


# ---------------------------------------------------------------- 🔑 passwords: at least 6 for new accounts

def test_a_new_account_needs_a_six_character_password(connect):
    client = connect()
    client.send({"type": "auth", "action": "register", "username": "Adi", "password": "12345"})
    result = client.expect(lambda m: m.get("type") == "auth_result")
    assert not result["ok"] and "6 to 64" in result["text"]
    client.send({"type": "auth", "action": "register", "username": "Adi", "password": "123456"})
    assert client.expect(lambda m: m.get("type") == "auth_result" and m.get("ok"))


def test_an_old_account_with_a_short_password_still_logs_in(connect):
    salt, digest = auth.hash_password("1234")
    state.accounts["old"] = {**storage.new_account("Old", salt, digest), "created": 0}
    client = connect()
    client.send({"type": "auth", "action": "login", "username": "Old", "password": "1234"})
    assert client.expect(lambda m: m.get("type") == "auth_result")["ok"]


def test_file_is_reserved_because_of_accept_file(connect):
    client = connect()
    client.send({"type": "auth", "action": "register", "username": "File", "password": "pass1234"})
    assert not client.expect(lambda m: m.get("type") == "auth_result")["ok"]
