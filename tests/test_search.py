"""🔎 /search word: finds it in the history of the rooms you're in (the lobby and your groups), newest first,
at most SEARCH_MAX results. Never other groups' chat."""
import pytest

from chatserver import config, history

pytestmark = pytest.mark.integration


def say(client, text):
    client.line(text)
    client.expect(lambda m: m.get("type") == "chat" and m.get("text") == text)


def results(client, word):
    client.line(f"/search {word}")
    return client.expect_text("🔎")["text"]


def test_finds_it_newest_first(user):
    adi = user("Adi")
    say(adi, "pizza at 7")
    say(adi, "no wait, PIZZA at 8")
    say(adi, "salad")
    found = results(adi, "pizza")
    assert "2 results" in found and found.index("at 8") < found.index("at 7") and "salad" not in found


def test_only_rooms_youre_in(user):
    adi, ben = user("Adi"), user("Ben")
    ben.line("/create Secret private")
    ben.expect_text("Created")
    say(ben, "secret pizza plan")
    ben.line("/lobby")
    ben.expect(lambda m: m.get("type") == "history" and m.get("key") == "lobby")
    say(ben, "lobby pizza")
    found = results(adi, "pizza")
    assert "lobby pizza" in found and "secret" not in found
    mine = results(ben, "pizza")
    assert "secret pizza plan" in mine and "Secret  " in mine     # the room's title is a column


def test_at_most_twenty(user, monkeypatch):
    adi = user("Adi")
    for i in range(config.SEARCH_MAX + 3):
        history.add("lobby", {"type": "chat", "time": "10:00", "name": "Adi", "badge": "", "text": f"fries {i}",
                              "action": False})
    found = results(adi, "fries")
    assert f"{config.SEARCH_MAX} results" in found and "fries 22" in found and "fries 0" not in found


def test_percent_and_underscore_are_plain_letters(user):
    adi = user("Adi")
    say(adi, "100% sure")
    say(adi, "1000 sure")
    found = results(adi, "100%")
    assert "100% sure" in found and "1000 sure" not in found


def test_nothing_found_and_bad_words(user):
    adi = user("Adi")
    assert "No messages" in results(adi, "zebra")
    adi.line("/search a")
    adi.expect_text("Use: /search", kind="error")
