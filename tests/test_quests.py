"""🎯 Daily quests: /quests shows three small tasks (the same for everyone, new every day); each pays once."""
import pytest

import games
from chatserver import config, matches, quests, state

pytestmark = pytest.mark.integration


@pytest.fixture
def these_quests(monkeypatch):
    """Make today's quests these, so the test doesn't depend on the date."""
    def pick(*ids):
        monkeypatch.setattr(quests, "todays", lambda: list(ids))
    return pick


def test_three_a_day_the_same_for_everyone_and_new_tomorrow():
    assert len(quests.pick_for("2026-10-30")) == 3 == len(set(quests.pick_for("2026-10-30")))
    assert quests.pick_for("2026-10-30") == quests.pick_for("2026-10-30")
    assert any(quests.pick_for(f"2026-11-{d:02}") != quests.pick_for("2026-10-30") for d in range(1, 10))


def test_quests_lists_progress(user, these_quests):
    these_quests("chat", "win", "dm")
    adi = user("Adi")
    adi.line("hello")
    adi.line("/quests")
    listing = adi.expect_text("🎯 Today's quests")["text"]
    assert "Send 10 messages  1/10" in listing and "⬜ Win a game  0/1" in listing


def test_ten_messages_pay_once(user, these_quests):
    these_quests("chat", "win", "dm")
    adi = user("Adi")
    before = state.accounts["adi"]["tokens"]
    for i in range(12):
        adi.line(f"msg {i}")
    adi.expect_text("🎯 Quest done: Send 10 messages! +20")
    adi.line("/quests")
    assert "✅ Send 10 messages  10/10" in adi.expect_text("🎯 Today's quests")["text"]
    assert state.accounts["adi"]["tokens"] == before + 20
    assert len([m for m in adi.messages if "Quest done" in str(m.get("text", ""))]) == 1


def test_a_played_win_counts_and_a_resign_at_once_doesnt(user, these_quests):
    these_quests("win", "play", "chat")
    adi, ben = user("Adi"), user("Ben")
    with state.lock:
        matches.start_match(games.TicTacToe, "adi", "ben", 0)
    ben.line("/resign")                                   # no moves: doesn't count
    adi.expect_text("YOU WON")
    assert "win" not in quests.progress_of("adi")["progress"]
    with state.lock:
        matches.start_match(games.TicTacToe, "adi", "ben", 0)
        match = state.matches["adi"]
        match.moves = {"adi": config.MIN_MOVES_FOR_BONUS, "ben": config.MIN_MOVES_FOR_BONUS}
        matches.finish_match(match, "adi")
    adi.expect_text("Quest done: Win a game")
    assert quests.progress_of("ben")["progress"]["play"] == 1


def test_finishing_a_wordle_counts_even_a_loss(user, these_quests):
    these_quests("wordle", "chat", "dm")
    adi = user("Adi")
    adi.line("/wordle")
    adi.expect(lambda m: m.get("kind") == "board")
    for word in ("aaaaa", "bbbbb", "ccccc", "ddddd", "eeeee", "fffff"):
        adi.line(f"/g {word}")
    adi.expect_text("Quest done: Finish a Wordle")


def test_a_private_message_counts(user, these_quests):
    these_quests("dm", "chat", "win")
    adi, _ = user("Adi"), user("Ben")
    adi.line("/send Ben hi")
    adi.expect_text("Quest done: Send someone a private message")


def test_yesterdays_progress_starts_again(user, these_quests):
    these_quests("chat", "win", "dm")
    adi = user("Adi")
    state.accounts["adi"]["quests"] = {"day": "2000-01-01", "progress": {"chat": 9}, "done": ["win"]}
    adi.line("one")
    adi.line("/quests")
    assert "1/10" in adi.expect_text("🎯 Today's quests")["text"]
