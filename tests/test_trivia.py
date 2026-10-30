"""🧠 Hashbrown trivia: /trivia (you pay like /ask) -> Hashbrown asks the room a question; the first right
answer within TRIVIA_SECONDS wins TRIVIA_REWARD tokens. Always against the fake AI server."""
import pytest

from chatserver import config, hashbrown_extras, state

pytestmark = pytest.mark.integration

QUESTION = "QUESTION: What is the capital of France?\nANSWER: Paris"


def ask_trivia(adi, fake_hashbrown):
    fake_hashbrown.answer = QUESTION
    adi.line("/trivia")
    return adi.expect(lambda m: m.get("type") == "chat" and "🧠" in m.get("text", ""))


def test_the_first_right_answer_wins(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    question = ask_trivia(adi, fake_hashbrown)
    assert "capital of France" in question["text"] and "Paris" not in question["text"]
    before = state.accounts["ben"]["tokens"]
    ben.line("london")
    ben.line("the PARIS!")
    ben.expect_text("🧠 Ben got it")
    assert state.accounts["ben"]["tokens"] == before + config.TRIVIA_REWARD
    assert "lobby" not in state.trivia


def test_time_up_reveals_the_answer(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    ask_trivia(adi, fake_hashbrown)
    with state.lock:
        hashbrown_extras.trivia_time_up("lobby", state.trivia["lobby"])
    assert "Paris" in ben.expect_text("⏰ Trivia over")["text"]


def test_a_reply_without_a_question_is_refunded(user, fake_hashbrown):
    adi = user("Adi")
    fake_hashbrown.answer = "I don't know any trivia, sorry"
    before = state.accounts["adi"]["tokens"]
    adi.line("/trivia")
    adi.expect_text("refunded", kind="error")
    assert state.accounts["adi"]["tokens"] == before


def test_one_trivia_at_a_time_per_room(user, fake_hashbrown):
    adi = user("Adi")
    ask_trivia(adi, fake_hashbrown)
    adi.line("/trivia")
    adi.expect_text("already a trivia question", kind="error")


def test_no_trivia_when_hashbrown_is_off(user):
    adi = user("Adi")
    adi.line("/trivia")
    adi.expect_text("asleep", kind="error")
