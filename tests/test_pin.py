"""📌 /pin text: the room's topic, shown at the top (a {"type": "topic"} packet for the website) and to anyone
who joins. In a group only its admins can pin; in the lobby only a server admin. /pin alone shows it,
/pin clear takes it away."""
import json

import pytest

from chatserver import config, state, storage

pytestmark = pytest.mark.integration


def topic_packet(client, empty=False):
    """The next topic packet with a topic in it (or, with empty=True, the next one that clears it)."""
    return client.expect(lambda m: m.get("type") == "topic" and bool(m.get("text")) != empty)


def group(owner, name="Potatoes"):
    owner.line(f"/create {name}")
    owner.expect_text("Created")


def test_a_group_admin_pins_and_the_room_sees_it(user):
    adi, ben = user("Adi"), user("Ben")
    group(adi)
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and m.get("key") == "potatoes")
    adi.line("/pin Movie night at 8")
    assert topic_packet(ben) == {"type": "topic", "room": "potatoes", "text": "Movie night at 8"}
    ben.expect_text("📌 Adi pinned: Movie night at 8")
    assert state.groups["potatoes"]["topic"] == "Movie night at 8"


def test_members_who_arent_admins_cant_pin(user):
    adi, ben = user("Adi"), user("Ben")
    group(adi)
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and m.get("key") == "potatoes")
    ben.line("/pin mine now")
    ben.expect_text("Only group admins", kind="error")


def test_joining_shows_the_topic(user):
    adi, ben = user("Adi"), user("Ben")
    group(adi)
    adi.line("/pin Be nice")
    adi.expect_text("📌")
    ben.line("/join Potatoes")
    assert topic_packet(ben)["text"] == "Be nice"      # the banner first, then the line in the chat
    ben.expect_text("📌 Topic: Be nice")


def test_moving_to_a_room_without_a_topic_clears_the_banner(user):
    adi = user("Adi")
    group(adi)
    adi.line("/pin Be nice")
    topic_packet(adi)
    adi.line("/lobby")
    assert topic_packet(adi, empty=True) == {"type": "topic", "room": "lobby", "text": ""}


def test_only_a_server_admin_pins_the_lobby(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/pin Welcome all")
    adi.expect_text("Only a server admin", kind="error")
    state.accounts["adi"]["admin"] = True
    adi.line("/pin Welcome all")
    assert topic_packet(ben)["text"] == "Welcome all"
    assert state.lobby_topic == "Welcome all"


def test_pin_alone_shows_and_clear_removes(user):
    adi = user("Adi")
    group(adi)
    adi.line("/pin")
    adi.expect_text("No topic pinned")
    adi.line("/pin Snacks")
    adi.expect_text("pinned: Snacks")
    adi.line("/pin")
    adi.expect_text("📌 Topic: Snacks")
    adi.line("/pin clear")
    assert topic_packet(adi, empty=True)["room"] == "potatoes"
    assert state.groups["potatoes"]["topic"] == ""


def test_logging_in_shows_the_lobby_topic_and_it_survives_a_restart(user, tmp_path, monkeypatch):
    state.lobby_topic = "Be kind"
    adi = user("Adi")
    adi.expect_text("📌 Topic: Be kind")
    path = tmp_path / "data.json"
    monkeypatch.setattr(config, "DATA_FILE", str(path))
    storage.save_data()
    assert json.loads(path.read_text(encoding="utf-8"))["lobby_topic"] == "Be kind"
    state.lobby_topic = ""
    assert storage.load_data() and state.lobby_topic == "Be kind"


def test_topics_are_short(user):
    adi = user("Adi")
    group(adi)
    adi.line("/pin " + "x" * 500)
    assert len(topic_packet(adi)["text"]) == config.TOPIC_MAX
