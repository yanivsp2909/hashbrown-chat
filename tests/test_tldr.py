"""📝 /tldr: Hashbrown sums up what the room talked about. Only you see it, and you pay like /ask."""
import pytest

from chatserver import config, state

pytestmark = pytest.mark.integration


def test_tldr_reads_more_history_and_answers_only_you(user, fake_hashbrown):
    adi, ben = user("Adi"), user("Ben")
    for i in range(config.HASHBROWN_HISTORY + 5):
        ben.line(f"message number {i}")
    ben.expect(lambda m: m.get("text") == f"message number {config.HASHBROWN_HISTORY + 4}")
    before = state.accounts["adi"]["tokens"]
    adi.line("/tldr")
    answer = adi.expect(lambda m: m.get("kind") == "private")
    assert answer["text"].startswith("🥔 Hashbrown (only you):")
    body = str(fake_hashbrown.requests[-1][1])
    assert "message number 0" in body                       # more than the usual 15 lines
    assert "Summarize" in body or "summar" in body.lower()
    first_question_reward = config.ACHIEVEMENTS["potato"][-1]   # 🥔 achievement for a first question
    assert state.accounts["adi"]["tokens"] == before - config.HASHBROWN_COST + first_question_reward
    ben.line("/users")
    ben.expect_text("Online now")
    assert not any("Hashbrown (only you)" in str(m.get("text")) for m in ben.messages)


def test_tldr_with_hashbrown_off_says_so(user):
    adi = user("Adi")
    adi.line("/tldr")
    adi.expect_text("Hashbrown", kind="error")
