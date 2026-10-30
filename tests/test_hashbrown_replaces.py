"""The "thinking" notice has a temp_id; the answer (or the error) says which notice it replaces."""
import pytest

from chatserver import config, history

pytestmark = pytest.mark.integration


def is_thinking(msg):
    return msg.get("type") == "msg" and "thinking" in msg.get("text", "")


def is_hashbrown_chat(msg):
    return msg.get("type") == "chat" and msg.get("name") == "Hashbrown"


def test_public_answer_replaces_the_thinking_notice_for_the_whole_room(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    adi.line("@hashbrown hi")
    thinking = ben.expect(is_thinking)
    assert thinking["kind"] == "event"
    assert thinking["temp_id"].startswith("hb-")
    answer = ben.expect(is_hashbrown_chat)
    assert answer["replaces"] == thinking["temp_id"]


def test_private_answer_replaces_the_thinking_notice(user, fake_hashbrown):
    adi = user("Adi")
    adi.line("/ask hi")
    thinking = adi.expect(is_thinking)
    answer = adi.expect(lambda m: m.get("kind") == "private")
    assert answer["replaces"] == thinking["temp_id"]


def test_the_error_replaces_the_thinking_notice(user, fake_hashbrown):
    adi = user("Adi")
    fake_hashbrown.status = 500
    adi.line("/ask hi")
    thinking = adi.expect(is_thinking)
    error = adi.expect_text("refunded", kind="error")
    assert error["replaces"] == thinking["temp_id"]


def test_public_error_replaces_the_thinking_notice(user, fake_hashbrown):
    adi = user("Adi")
    fake_hashbrown.status = 500
    adi.line("@hashbrown hi")
    thinking = adi.expect(is_thinking)
    error = adi.expect_text("refunded", kind="error")
    assert error["replaces"] == thinking["temp_id"]


def test_every_question_gets_its_own_temp_id(user, fake_hashbrown, monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_COOLDOWN", 0)
    adi = user("Adi")
    adi.line("/ask one")
    first = adi.expect(is_thinking)
    adi.expect(lambda m: m.get("kind") == "private")
    adi.line("/ask two")
    second = adi.expect(is_thinking)
    assert first["temp_id"] != second["temp_id"]


def test_other_messages_have_no_replaces_and_history_does_not_keep_it(user, fake_hashbrown):
    adi = user("Adi")
    adi.line("hello")
    chat = adi.expect(lambda m: m.get("type") == "chat")
    assert "replaces" not in chat and "temp_id" not in chat
    adi.line("@hashbrown hi")
    adi.expect(is_hashbrown_chat)
    assert all("replaces" not in m for m in history.recent("lobby"))
