"""👤 Profiles: new optional account fields (old saves still load). /profile [name] shows a card,
/setprofile field value changes yours, /password old new changes the password (the old one first).
The website asks with {"type": "get_profile", "name"} and gets {"type": "profile", "profile"}; your own profile
also comes at login to clients that said "profiles". The username never changes."""
import json

import pytest

from chatserver import auth, config, state, storage

pytestmark = pytest.mark.integration


def card(client, name=""):
    client.line(f"/profile {name}".strip())
    return client.expect_text("👤")["text"]


def setp(client, field, value, ok=True):
    client.line(f"/setprofile {field} {value}".rstrip())
    return client.expect(lambda m: m.get("kind") == ("system" if ok else "error") and "👤" in m.get("text", ""))["text"]


def test_new_and_old_accounts_have_the_fields(tmp_path, monkeypatch):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"accounts": {"zed": {"login": "Zed", "nick": "Zed", "salt": "00", "hash": "00",
                                                     "tokens": 5}}, "groups": {}}), encoding="utf-8")
    monkeypatch.setattr(config, "DATA_FILE", str(path))
    assert storage.load_data()
    zed = state.accounts["zed"]
    assert zed["avatar"] == "" and zed["status"] == "online" and zed["privacy"] == {"last_seen": True, "dms": "everyone"}


def test_set_and_show_the_profile(user):
    adi, ben = user("Adi"), user("Ben")
    setp(adi, "avatar", "🍟")
    setp(adi, "bio", "I like fries and chess")
    setp(adi, "status", "busy")
    setp(adi, "statustext", "doing homework")
    setp(adi, "game", "connect4")
    setp(adi, "color", "3")
    shown = card(ben, "Adi")
    for part in ("🍟", "Adi", "I like fries and chess", "busy", "doing homework", "Connect 4"):
        assert part in shown
    assert state.accounts["adi"]["color"] == 3


@pytest.mark.parametrize("field, value", [("avatar", "ab"), ("avatar", "🍟🍟"), ("status", "sleeping"),
                                          ("color", "9"), ("game", "chess"), ("theme", "blue"), ("dms", "some"),
                                          ("bio", "x" * 200), ("nope", "1")])
def test_bad_values_say_what_is_allowed(user, field, value):
    adi = user("Adi")
    setp(adi, field, value, ok=False)


def test_the_name_field_is_the_same_as_nick(user):
    adi = user("Adi")
    adi.line("/setprofile name Spud")
    adi.expect_text("is now called")
    assert state.accounts["adi"]["nick"] == "Spud" and state.accounts["adi"]["login"] == "Adi"


def test_the_theme_is_remembered_and_comes_at_login(user):
    adi = user("Adi", features=["profiles"])
    setp(adi, "theme", "light")
    adi.close()
    again = user("Adi", action="login", features=["profiles"])
    mine = again.expect(lambda m: m.get("type") == "profile")
    assert mine["mine"] is True and mine["profile"]["theme"] == "light"


def test_the_website_asks_for_a_profile(user):
    adi, ben = user("Adi"), user("Ben")
    setp(adi, "bio", "hello")
    ben.send({"type": "get_profile", "name": "Adi"})
    profile = ben.expect(lambda m: m.get("type") == "profile")["profile"]
    assert profile["name"] == "Adi" and profile["bio"] == "hello" and profile["online"] is True
    assert "privacy" not in profile and "theme" not in profile and "hash" not in profile and "salt" not in profile
    ben.send({"type": "get_profile", "name": "Nobody"})
    ben.expect_text("No one called", kind="error")


def test_last_seen_can_be_hidden(user):
    adi, ben = user("Adi"), user("Ben")
    adi.close()
    ben.expect_text("Adi left the chat")
    assert "Last seen" in card(ben, "Adi")
    state.accounts["adi"]["privacy"]["last_seen"] = False
    assert "Last seen" not in card(ben, "Adi")


def test_who_can_send_you_private_messages(user):
    adi, ben = user("Adi"), user("Ben")
    setp(adi, "dms", "nobody")
    ben.line("/send Adi hi")
    ben.expect_text("doesn't take private messages", kind="error")
    setp(adi, "dms", "groups")
    ben.line("/send Adi hi")
    ben.expect_text("only takes private messages from people in their groups", kind="error")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and m.get("key") == "potatoes")
    ben.line("/send Adi hi")
    adi.expect(lambda m: m.get("kind") == "private")


def test_changing_the_password_needs_the_old_one(user, connect):
    adi = user("Adi")
    adi.line("/password wrong newpass1")
    adi.expect_text("old password is wrong", kind="error")
    adi.line("/password pass1234 abc")
    adi.expect_text("6 to 64", kind="error")
    adi.line("/password pass1234 newpass1")
    adi.expect_text("Password changed")
    salt, digest = auth.hash_password("newpass1", state.accounts["adi"]["salt"])
    assert digest == state.accounts["adi"]["hash"]


def test_the_website_changes_the_password_with_its_own_packet(user):
    adi = user("Adi")
    adi.send({"type": "change_password", "old": "pass1234", "new": "brandnew9"})
    adi.expect_text("Password changed")


def test_the_last_seen_time_is_saved_when_you_leave(user):
    adi, ben = user("Adi"), user("Ben")
    adi.close()
    ben.expect_text("Adi left the chat")
    assert state.accounts["adi"]["last_seen"] > 0


# ---------------------------------------------------------------- the avatar and name colour on chat bubbles

def test_chat_and_history_carry_the_senders_avatar_and_colour(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/setprofile avatar 🍟")
    adi.line("/setprofile color 3")
    adi.expect_text("Saved your color")
    adi.line("hello fries")
    got = ben.expect(lambda m: m.get("type") == "chat" and m.get("text") == "hello fries")
    assert (got["avatar"], got["color"]) == ("🍟", 3)
    ben.line("plain me")
    plain = adi.expect(lambda m: m.get("type") == "chat" and m.get("text") == "plain me")
    assert "avatar" not in plain and "color" not in plain     # nothing set: nothing extra
    cat = user("Cat")
    history = cat.messages[-1] if cat.messages[-1].get("type") == "history" else next(
        m for m in reversed(cat.messages) if m.get("type") == "history")
    mine = next(m for m in history["messages"] if m["text"] == "hello fries")
    assert (mine["avatar"], mine["color"]) == ("🍟", 3)
