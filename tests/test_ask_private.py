"""/ask is private: nothing goes to the room, the answer goes only to the asker, who always pays."""
import pytest

from chatserver import config, state

pytestmark = pytest.mark.integration

PRIVATE_PREFIX = "🥔 Hashbrown (only you): "


def is_private_answer(msg):
    return msg.get("kind") == "private" and msg.get("text", "").startswith(PRIVATE_PREFIX)


def test_ask_answers_only_the_asker(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/ask tell me a joke")
    answer = adi.expect(is_private_answer)
    assert answer["text"] == PRIVATE_PREFIX + fake_hashbrown.answer
    ben.sync()
    assert not any("tell me a joke" in text or fake_hashbrown.answer in text for text in ben.texts())
    assert not any(m.get("type") == "chat" and m.get("name") == "Hashbrown" for m in ben.messages)


def test_ask_does_not_post_the_question_to_the_room(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/ask secret question")
    adi.expect(is_private_answer)
    ben.sync()
    assert not any(m.get("type") == "chat" for m in ben.messages)
    assert not any(m.get("type") == "chat" for m in adi.messages)


def test_ask_is_paid_by_the_asker_even_inside_a_group_with_the_upgrade(user, fake_hashbrown):
    adi = user("Adi")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    with state.lock:
        state.groups["potatoes"]["upgrades"].append("hashbrown")
        state.groups["potatoes"]["bank"] = 300
        before = state.accounts["adi"]["tokens"]
    adi.line("/ask hi")
    adi.expect(is_private_answer)
    adi.expect_text("ACHIEVEMENT UNLOCKED: 🥔")  # the first question also pays a one-time reward
    reward = config.ACHIEVEMENTS["potato"][3]
    assert state.groups["potatoes"]["bank"] == 300
    assert state.accounts["adi"]["tokens"] == before - config.HASHBROWN_COST + reward


def test_a_muted_user_can_ask(user, fake_hashbrown):
    adi = user("Adi")
    with state.lock:
        state.mutes[("lobby", "adi")] = 9_999_999_999
    adi.line("/ask hi")
    adi.expect(is_private_answer)


def test_a_failed_ask_is_refunded_to_the_asker_privately(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    fake_hashbrown.status = 500
    before = state.accounts["adi"]["tokens"]
    adi.line("/ask hi")
    adi.expect_text("refunded")
    assert state.accounts["adi"]["tokens"] == before
    assert state.hashbrown_today.get("adi", ("", 0))[1] == 0
    ben.sync()
    assert not any("refunded" in text for text in ben.texts())


def test_ask_thinking_notice_goes_only_to_the_asker(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    fake_hashbrown.delay = 0.3
    adi.line("/ask hi")
    adi.expect_text("thinking")
    adi.expect(is_private_answer)
    ben.sync()
    assert not any("thinking" in text for text in ben.texts())


def test_ask_without_tokens_is_refused(user, fake_hashbrown):
    adi = user("Adi")
    with state.lock:
        state.accounts["adi"]["tokens"] = 0
    adi.line("/ask hi")
    adi.expect_text("costs", kind="error")
    assert fake_hashbrown.requests == []


def test_at_hashbrown_in_chat_stays_public(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    adi.line("@hashbrown hi")
    ben.expect(lambda m: m.get("type") == "chat" and m.get("name") == "Hashbrown")
