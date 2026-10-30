"""🥔 Hashbrown extras: the game commentator, a group personality, /judge, Wordle /hint, /tr and the
question of the day. Always against the fake AI server, never the real one."""
import pytest

import games
from chatserver import config, hashbrown_extras, history, matches, state

pytestmark = pytest.mark.integration


def request_text(foundry):
    return str(foundry.requests[-1][1])


# ---------------------------------------------------------------- 🎙️ game commentator

def test_after_a_match_hashbrown_comments_to_both_players(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    with state.lock:
        matches.start_match(games.TicTacToe, "adi", "ben", 0)
    adi.line("/resign")
    for player in (adi, ben):
        assert player.expect_text("🎙️ Hashbrown:")["text"].endswith(fake_hashbrown.answer)
    assert "Tic-Tac-Toe" in request_text(fake_hashbrown)


def test_no_commentator_when_switched_off_or_hashbrown_is_off(user, monkeypatch):
    adi, ben = user("Adi"), user("Ben")      # no fake_hashbrown: Hashbrown is off
    with state.lock:
        matches.start_match(games.TicTacToe, "adi", "ben", 0)
    adi.line("/resign")
    ben.expect_text("YOU WON")
    adi.line("/users")
    adi.expect_text("Online now")
    assert not any("🎙️" in str(m.get("text")) for m in adi.messages)


# ---------------------------------------------------------------- 🎭 group personality

def test_a_group_with_the_upgrade_gives_hashbrown_its_personality(user, fake_hashbrown, monkeypatch):
    adi = user("Adi")
    adi.line("/create Pirates")
    adi.expect_text("Created")
    adi.line("/personality a pirate who loves potatoes")
    adi.expect_text("needs the 🎭 personality upgrade", kind="error")
    state.groups["pirates"]["bank"] = 1000
    adi.line("/upgrade personality")
    adi.expect_text("personality")
    adi.line("/personality a pirate who loves potatoes")
    adi.expect_text("🎭 Hashbrown's personality here")
    adi.line("@hashbrown hi")
    adi.expect(lambda m: m.get("type") == "chat" and m.get("name") == "Hashbrown")
    assert "a pirate who loves potatoes" in request_text(fake_hashbrown)


def test_only_group_admins_set_the_personality(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/create Pirates")
    adi.expect_text("Created")
    ben.line("/join Pirates")
    ben.expect(lambda m: m.get("type") == "history")
    ben.line("/personality grumpy")
    ben.expect_text("admins", kind="error")


# ---------------------------------------------------------------- ⚖️ /judge and 🌐 /tr

def test_judge_reads_the_debate_and_answers_the_room(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    adi.line("pizza is the best")
    adi.expect(lambda m: m.get("text") == "pizza is the best")
    ben.line("no, falafel is")
    adi.expect(lambda m: m.get("text") == "no, falafel is")   # both are in the history before /judge reads it
    adi.line("/judge")
    verdict = ben.expect(lambda m: m.get("type") == "chat" and m.get("name") == "Hashbrown")
    assert verdict["text"] == fake_hashbrown.answer
    assert "falafel is" in request_text(fake_hashbrown) and "judge" in request_text(fake_hashbrown).lower()


def test_tr_translates_privately(user, fake_hashbrown):
    adi = user("Adi")
    adi.line("/tr שלום לכולם")
    answer = adi.expect(lambda m: m.get("kind") == "private")
    assert answer["text"].startswith("🥔 Hashbrown (only you):")
    assert "שלום לכולם" in request_text(fake_hashbrown)


def test_tr_needs_text(user):
    adi = user("Adi")
    adi.line("/tr")
    adi.expect_text("/tr text", kind="error")


# ---------------------------------------------------------------- 🟩 Wordle /hint

def start_wordle(adi, answer="crane"):
    adi.line("/wordle")
    adi.expect(lambda m: m.get("kind") == "board")
    state.solo["adi"].answer = answer


def test_hint_asks_hashbrown_but_never_shows_the_word(user, fake_hashbrown):
    fake_hashbrown.answer = "It starts like CRANE does, think of birds"
    adi = user("Adi")
    start_wordle(adi)
    adi.line("/hint")
    hint = adi.expect(lambda m: m.get("kind") == "private")["text"]
    assert "crane" not in hint.lower() and "•••••" in hint


def test_one_hint_per_game_and_only_during_a_wordle(user, fake_hashbrown):
    adi = user("Adi")
    adi.line("/hint")
    adi.expect_text("Start a /wordle first", kind="error")
    start_wordle(adi)
    adi.line("/hint")
    adi.expect(lambda m: m.get("kind") == "private")
    adi.line("/hint")
    adi.expect_text("one hint per game", kind="error")


def test_without_hashbrown_the_hint_shows_a_letter(user):
    adi = user("Adi")
    start_wordle(adi, "crane")
    adi.line("/hint")
    hint = adi.expect_text("💡")["text"]
    assert any(f"letter {i + 1} is {c.upper()}" in hint for i, c in enumerate("crane"))


# ---------------------------------------------------------------- ❓ question of the day

def test_question_of_the_day_is_posted_once_in_the_lobby(user, fake_hashbrown, monkeypatch):
    monkeypatch.setattr(config, "QOTD_HOUR", 0)
    adi, _ = user("Adi"), user("Ben")
    hashbrown_extras.question_of_the_day_tick()
    question = adi.expect(lambda m: m.get("type") == "chat" and m.get("name") == "Hashbrown")
    assert question["text"].startswith("❓ Question of the day:")
    assert any("Question of the day" in m["text"] for m in history.recent("lobby"))
    hashbrown_extras.question_of_the_day_tick()          # the same day: nothing new
    adi.line("/qotd")
    assert adi.expect_text("❓")["text"].endswith(fake_hashbrown.answer)
    assert len(fake_hashbrown.requests) == 1


def test_no_question_of_the_day_when_alone_or_hashbrown_is_off(user, monkeypatch):
    monkeypatch.setattr(config, "QOTD_HOUR", 0)
    adi = user("Adi")
    hashbrown_extras.question_of_the_day_tick()
    adi.line("/qotd")
    adi.expect_text("No question of the day yet")



def test_a_hint_hides_the_word_even_spelled_out(user, fake_hashbrown):
    fake_hashbrown.answer = "It's C r-a n e, a bird"
    adi = user("Adi")
    start_wordle(adi)
    adi.line("/hint")
    assert "•••••" in adi.expect(lambda m: m.get("kind") == "private")["text"]


def test_a_refused_hint_isnt_used_up(user, fake_hashbrown):
    adi = user("Adi")
    start_wordle(adi)
    state.accounts["adi"]["tokens"] = 0          # can't pay: Hashbrown refuses
    adi.line("/hint")
    adi.expect_text("costs", kind="error")
    assert not getattr(state.solo["adi"], "hinted", False)
