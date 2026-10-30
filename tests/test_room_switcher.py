"""💬 The chat switcher: clients that say "rooms" at login get the list of their rooms, and the chat
from all of them (each message tagged with its room), so the website can show unread counts.
Old clients (no "rooms") get exactly what they always got."""
import pytest

from chatserver import state

pytestmark = pytest.mark.integration


@pytest.fixture
def switcher_user(connect):
    """switcher_user("Adi") -> a FakeClient logged in with the "rooms" feature."""
    def make(name):
        client = connect()
        client.send({"type": "auth", "action": "register", "username": name, "password": "pass1234",
                     "features": ["rooms"]})
        assert client.expect(lambda m: m.get("type") == "auth_result")["ok"]
        client.expect(lambda m: m.get("type") == "history")
        return client
    return make


def last_room_list(client):
    return client.expect(lambda m: m.get("type") == "rooms")


def group_with(owner, name="Potatoes"):
    owner.line(f"/create {name}")
    owner.expect_text("Created")


def test_the_room_list_comes_at_login_and_when_you_join_or_leave(switcher_user, user):
    adi = switcher_user("Adi")
    first = last_room_list(adi)
    assert first["rooms"] == [{"key": "lobby", "name": "Lobby", "title": "🏠 Lobby"}] and first["current"] == "lobby"
    group_with(adi)
    rooms = last_room_list(adi)
    assert [r["key"] for r in rooms["rooms"]] == ["lobby", "potatoes"] and rooms["current"] == "potatoes"
    adi.line("/lobby")
    assert last_room_list(adi)["current"] == "lobby"


def test_old_clients_get_no_room_list(user):
    ben = user("Ben")
    ben.line("/create Potatoes")
    ben.expect_text("Created")
    ben.line("/users")
    ben.expect_text("Online now")
    assert not any(m.get("type") == "rooms" for m in ben.messages)


def test_chat_from_your_other_rooms_reaches_you_tagged_with_the_room(switcher_user, user):
    adi = switcher_user("Adi")
    ben = user("Ben")
    group_with(ben)
    adi.line("/join Potatoes")
    adi.expect(lambda m: m.get("type") == "history")
    adi.line("/lobby")
    adi.expect(lambda m: m.get("type") == "history")
    ben.line("group news")                                   # Ben is in the group, Adi is in the lobby
    msg = adi.expect(lambda m: m.get("type") == "chat" and m.get("text") == "group news")
    assert msg["room"] == "potatoes"


def test_lobby_chat_reaches_you_in_a_group_and_your_own_room_is_tagged_too(switcher_user, user):
    adi = switcher_user("Adi")
    ben = user("Ben")
    group_with(adi)
    ben.line("lobby talk")
    assert adi.expect(lambda m: m.get("text") == "lobby talk")["room"] == "lobby"
    adi.line("in my group")
    assert adi.expect(lambda m: m.get("text") == "in my group")["room"] == "potatoes"


def test_old_clients_still_only_get_their_own_room(user):
    adi, ben = user("Adi"), user("Ben")
    group_with(ben)
    ben.line("secret group plans")
    adi.line("/users")
    adi.expect_text("Online now")
    assert not any(m.get("text") == "secret group plans" for m in adi.messages)


def test_non_members_never_get_a_groups_chat(switcher_user, user):
    adi = switcher_user("Adi")
    ben = user("Ben")
    group_with(ben)
    ben.line("members only")
    adi.line("/users")
    adi.expect_text("Online now")
    assert not any(m.get("text") == "members only" for m in adi.messages)


def test_being_approved_or_kicked_updates_the_list_without_moving_you(switcher_user, user):
    ben = user("Ben")
    ben.line("/create Potatoes private")
    ben.expect_text("Created")
    adi = switcher_user("Adi")
    last_room_list(adi)
    adi.line("/join Potatoes")
    ben.expect_text("wants to join")
    ben.line("/approve Adi")
    assert [r["key"] for r in last_room_list(adi)["rooms"]] == ["lobby", "potatoes"]
    ben.line("/kick Adi")
    assert [r["key"] for r in last_room_list(adi)["rooms"]] == ["lobby"]
    assert state.online["adi"].room == "lobby"


def test_a_rooms_history_says_which_room_it_is(switcher_user):
    """The website keeps one message list per room: the history packet's "key" says whose list it is
    (its "room" is only the title, for showing)."""
    adi = switcher_user("Adi")
    group_with(adi)
    assert adi.expect(lambda m: m.get("type") == "history" and m.get("key") == "potatoes")["room"] == "#Potatoes"
    adi.line("/lobby")
    assert adi.expect(lambda m: m.get("type") == "history")["key"] == "lobby"
