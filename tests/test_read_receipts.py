"""✓✓ Read receipts for private messages: your copy of a /send carries "pm": {"id", "status": "sent"};
{"type": "receipt", "id", "status": "delivered"} comes once it really went out to them, and "seen" once their
app says {"type": "seen", "id"} (the website does when the message is on screen). Old clients ignore all this."""
import pytest

from chatserver import config, state

pytestmark = pytest.mark.integration


def pm(sender, to, text):
    sender.line(f"/send {to} {text}")
    mine = sender.expect(lambda m: m.get("kind") == "private" and text in m.get("text", ""))
    return mine


def receipts(client, pm_id):
    return [m["status"] for m in client.messages if m.get("type") == "receipt" and m.get("id") == pm_id]


def test_delivered_then_seen(user):
    adi, ben = user("Adi"), user("Ben")
    mine = pm(adi, "Ben", "psst")
    pm_id = mine["pm"]["id"]
    assert mine["pm"]["status"] == "sent"
    theirs = ben.expect(lambda m: m.get("kind") == "private")
    assert theirs["pm_id"] == pm_id
    adi.expect(lambda m: m.get("type") == "receipt" and m.get("status") == "delivered")
    ben.send({"type": "seen", "id": pm_id})
    assert adi.expect(lambda m: m.get("type") == "receipt" and m.get("status") == "seen")["id"] == pm_id


def test_only_the_receiver_can_say_seen_and_only_once(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    pm_id = pm(adi, "Ben", "psst")["pm"]["id"]
    adi.expect(lambda m: m.get("type") == "receipt")
    cat.send({"type": "seen", "id": pm_id})        # not theirs
    adi.send({"type": "seen", "id": pm_id})        # the sender can't either
    ben.send({"type": "seen", "id": pm_id})
    ben.send({"type": "seen", "id": pm_id})        # twice
    ben.send({"type": "seen", "id": "x"})          # nonsense
    adi.expect(lambda m: m.get("type") == "receipt" and m.get("status") == "seen")
    adi.line("/users")
    adi.expect_text("Online now")
    assert receipts(adi, pm_id) == ["delivered", "seen"]


def test_offline_messages_have_no_receipts(user):
    adi, ben = user("Adi"), user("Ben")
    ben.close()
    adi.line("/users")
    adi.expect_text("Online now (1)")
    adi.line("/send Ben later")
    note = adi.expect_text("offline")
    assert "pm" not in note


def test_old_receipts_are_forgotten(user, monkeypatch):
    monkeypatch.setattr(config, "RECEIPTS_KEEP", 2)
    adi, ben = user("Adi"), user("Ben")
    first = pm(adi, "Ben", "one")["pm"]["id"]
    for text in ("two", "three"):
        pm(adi, "Ben", text)
    assert first not in state.pms and len(state.pms) == 2
    ben.send({"type": "seen", "id": first})        # too old: nothing happens
    adi.line("/users")
    adi.expect_text("Online now")
    assert "seen" not in receipts(adi, first)


def test_seen_doesnt_count_toward_the_spam_limit(user, monkeypatch):
    monkeypatch.setattr(config, "SPAM_LIMIT", 2)
    adi, ben = user("Adi"), user("Ben")
    for _ in range(5):
        ben.send({"type": "seen", "id": 999})
    ben.line("still fine")
    adi.expect(lambda m: m.get("text") == "still fine")
