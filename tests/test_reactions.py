"""😂 Reactions: {"type": "react", "id": message id, "emoji": "👍"} toggles your reaction on a chat message.
The room gets {"type": "reactions", "id", "counts": {"👍": 2}}, and the room history carries them too."""
import pytest

from chatserver import config

pytestmark = pytest.mark.integration


def post(client, text):
    client.line(text)
    return client.expect(lambda m: m.get("type") == "chat" and m.get("text") == text)["id"]


def reactions_for(client, message_id):
    return client.expect(lambda m: m.get("type") == "reactions" and m.get("id") == message_id)


def test_a_reaction_reaches_the_room_with_the_counts(user):
    adi, ben = user("Adi"), user("Ben")
    message_id = post(adi, "pizza tonight?")
    ben.send({"type": "react", "id": message_id, "emoji": "👍"})
    assert reactions_for(adi, message_id)["counts"] == {"👍": 1}
    adi.send({"type": "react", "id": message_id, "emoji": "👍"})
    ben.expect(lambda m: m.get("type") == "reactions" and m.get("counts") == {"👍": 2})   # both counted


def test_reacting_again_takes_it_back(user):
    adi = user("Adi")
    message_id = post(adi, "hello")
    adi.send({"type": "react", "id": message_id, "emoji": "😂"})
    reactions_for(adi, message_id)
    adi.send({"type": "react", "id": message_id, "emoji": "😂"})
    assert adi.expect(lambda m: m.get("type") == "reactions" and m.get("counts") == {})["id"] == message_id


@pytest.mark.parametrize("packet", [{"id": 1, "emoji": "🍕"}, {"id": "x", "emoji": "👍"}, {"id": 99999, "emoji": "👍"}])
def test_bad_reactions_are_refused(user, packet):
    adi = user("Adi")
    post(adi, "something")
    adi.send({"type": "react", **packet})
    adi.expect_text("Can't react", kind="error")


def test_you_cant_react_in_a_group_youre_not_in(user):
    adi, ben = user("Adi"), user("Ben")
    ben.line("/create Potatoes")
    ben.expect_text("Created")
    message_id = post(ben, "members only")
    adi.send({"type": "react", "id": message_id, "emoji": "👍"})
    adi.expect_text("Can't react", kind="error")


def test_the_room_history_remembers_reactions(user):
    adi, ben = user("Adi"), user("Ben")
    message_id = post(adi, "remember me")
    ben.send({"type": "react", "id": message_id, "emoji": "❤️"})
    reactions_for(adi, message_id)
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    adi.line("/lobby")
    past = adi.expect(lambda m: m.get("type") == "history" and "Lobby" in m.get("room", ""))["messages"]
    assert next(m for m in past if m["id"] == message_id)["reactions"] == {"❤️": 1}


def test_the_allowed_emojis_are_a_setting():
    assert "👍" in config.REACTIONS and len(config.REACTIONS) <= 8
