"""💡 /answer: one answer per person to today's question of the day, posted in the lobby as
"💡 {nick}'s answer: ...". People vote with reactions; when the next question comes, the answer with the most
reactions (from other people) wins QOTD_PRIZE and Hashbrown announces it (no AI call for that)."""
import json

import pytest

from chatserver import config, hashbrown_extras, history, qotd, state, storage, textutil

pytestmark = pytest.mark.integration


def ask_today(question="What's the best fry?"):
    state.qotd = (textutil.today(), question)


def answer(client, text):
    client.line(f"/answer {text}")
    return client.expect(lambda m: m.get("type") == "chat" and m.get("text", "").endswith(f"'s answer: {text}"))


def test_an_answer_is_posted_in_the_lobby_as_a_card(user):
    adi, ben = user("Adi"), user("Ben")
    ask_today()
    card = answer(adi, "curly fries")
    assert card["text"] == "💡 Adi's answer: curly fries" and isinstance(card["id"], int)
    assert ben.expect(lambda m: m.get("id") == card["id"])
    assert any(m["text"] == card["text"] for m in history.recent("lobby"))


def test_one_answer_per_person_per_day(user):
    adi = user("Adi")
    ask_today()
    answer(adi, "curly fries")
    adi.line("/answer waffle fries")
    adi.expect_text("already answered", kind="error")


def test_no_question_no_answer_and_an_empty_answer_shows_how(user):
    adi = user("Adi")
    adi.line("/answer something")
    adi.expect_text("No question of the day", kind="error")
    ask_today()
    adi.line("/answer")
    adi.expect_text("/answer", kind="error")


def test_answering_from_a_group_still_posts_in_the_lobby(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    ask_today()
    adi.line("/answer hash browns")
    assert ben.expect(lambda m: m.get("type") == "chat")["text"] == "💡 Adi's answer: hash browns"


def vote(client, message_id, emoji="👍"):
    client.send({"type": "react", "id": message_id, "emoji": emoji})
    client.expect(lambda m: m.get("type") == "reactions" and m.get("id") == message_id)


def next_question(monkeypatch, fake_hashbrown):
    """It's tomorrow and Hashbrown asks a new question: yesterday's answers are settled first."""
    monkeypatch.setattr(config, "QOTD_HOUR", 0)
    state.qotd = ("2000-01-01", state.qotd[1])
    state.qotd_answers = {**state.qotd_answers, "day": "2000-01-01"}
    hashbrown_extras.question_of_the_day_tick()


def test_the_answer_with_the_most_reactions_wins_the_prize(user, fake_hashbrown, monkeypatch):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    ask_today()
    adis, bens = answer(adi, "curly"), answer(ben, "waffle")
    vote(cat, bens["id"])
    vote(adi, bens["id"], "😂")
    vote(ben, adis["id"])
    vote(ben, bens["id"])                     # your own answer doesn't count
    before = state.accounts["ben"]["tokens"]
    next_question(monkeypatch, fake_hashbrown)
    news = cat.expect(lambda m: m.get("type") == "chat" and "best answer" in m.get("text", ""))
    assert news["name"] == "Hashbrown" and "Ben" in news["text"] and str(config.QOTD_PRIZE) in news["text"]
    assert state.accounts["ben"]["tokens"] == before + config.QOTD_PRIZE
    cat.expect(lambda m: m.get("type") == "chat" and m.get("text", "").startswith("❓ Question of the day:"))
    assert len(fake_hashbrown.requests) == 1   # only the new question asked the AI
    assert state.qotd_answers["answers"] == []


def test_no_reactions_no_winner(user, fake_hashbrown, monkeypatch):
    adi, ben = user("Adi"), user("Ben")
    ask_today()
    answer(adi, "curly")
    before = state.accounts["adi"]["tokens"]
    next_question(monkeypatch, fake_hashbrown)
    ben.expect(lambda m: m.get("type") == "chat" and m.get("text", "").startswith("❓ Question of the day:"))
    assert state.accounts["adi"]["tokens"] == before
    assert not [m for m in ben.messages if "best answer" in str(m.get("text", ""))]


def test_answers_and_the_question_survive_a_restart(user, tmp_path, monkeypatch):
    adi = user("Adi")
    ask_today()
    answer(adi, "curly")
    path = tmp_path / "data.json"
    monkeypatch.setattr(config, "DATA_FILE", str(path))
    storage.save_data()
    saved = json.loads(path.read_text(encoding="utf-8"))["qotd"]
    assert saved["question"] == "What's the best fry?" and saved["answers"][0]["login"] == "adi"
    state.qotd, state.qotd_answers = None, qotd.empty()
    assert storage.load_data()
    assert state.qotd == (textutil.today(), "What's the best fry?")
    assert state.qotd_answers["answers"][0]["login"] == "adi"


def test_an_old_save_without_the_question_loads(tmp_path, monkeypatch):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"accounts": {}, "groups": {}}), encoding="utf-8")
    monkeypatch.setattr(config, "DATA_FILE", str(path))
    assert storage.load_data()
    assert state.qotd_answers == qotd.empty()
