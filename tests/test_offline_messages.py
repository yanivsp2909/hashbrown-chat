"""📬 Offline messages: /send to someone who is offline is kept and delivered when they log in."""
import pytest

from chatserver import config, state

pytestmark = pytest.mark.integration


def test_a_message_to_someone_offline_waits_for_them(user):
    ben = user("Ben")
    ben.close()
    adi = user("Adi")
    adi.line("/send Ben see you at 8")
    adi.expect_text("📬 Ben is offline")
    ben = user("Ben", action="login")
    note = ben.expect_text("see you at 8")
    assert note["kind"] == "private" and note["text"].startswith("💌 [") and "Adi → you: see you at 8" in note["text"]
    assert state.accounts["ben"]["inbox"] == []


def test_the_inbox_has_a_limit(user):
    ben = user("Ben")
    ben.close()
    adi = user("Adi")
    for i in range(config.OFFLINE_MAX + 2):
        adi.line(f"/send Ben note {i}")
    adi.expect_text("inbox is full", kind="error")
    assert len(state.accounts["ben"]["inbox"]) == config.OFFLINE_MAX


def test_unknown_names_are_still_an_error(user):
    adi = user("Adi")
    adi.line("/send Nobody hi")
    adi.expect_text("Nobody", kind="error")
