"""⏰ /remind 10m text: a private reminder later. At most REMIND_MAX waiting per person, up to REMIND_MAX_HOURS
ahead, saved in chat_data.json so a restart doesn't lose them. Due while you're away: you get it when you log in."""
import json
import time

import pytest

from chatserver import config, reminders, state, storage

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("text, seconds", [("10m", 600), ("2h", 7200), ("1h30m", 5400), ("90s", 90),
                                           ("24h", 86400), ("1H", 3600)])
def test_durations(text, seconds):
    assert reminders.parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "10", "m", "0m", "25h", "10x", "-5m", "1h1h", "99999999999m"])
def test_bad_durations(text):
    assert reminders.parse_duration(text) is None


def test_a_reminder_comes_privately_when_its_due(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/remind 10m take the fries out")
    adi.expect_text("I'll remind you in 10 min")
    with state.lock:
        reminders.deliver_due(now=time.time() + 601)
    note = adi.expect_text("⏰ Reminder: take the fries out")
    assert note["kind"] == "event"
    assert state.reminders == []
    ben.line("/users")
    ben.expect_text("Online now")
    assert not [m for m in ben.messages if "Reminder" in str(m.get("text", ""))]


def test_not_before_its_time(user):
    adi = user("Adi")
    adi.line("/remind 10m later")
    adi.expect_text("I'll remind you")
    with state.lock:
        reminders.deliver_due(now=time.time() + 300)
    assert len(state.reminders) == 1


def test_at_most_five_waiting(user):
    adi = user("Adi")
    for i in range(config.REMIND_MAX):
        adi.line(f"/remind 1h number {i}")
        adi.expect_text(f"I'll remind you")
    adi.line("/remind 1h one too many")
    adi.expect_text(f"at most {config.REMIND_MAX}", kind="error")


def test_bad_input_shows_how(user):
    adi = user("Adi")
    adi.line("/remind 30h too far")
    adi.expect_text("Use: /remind", kind="error")
    adi.line("/remind 10m")
    adi.expect_text("Use: /remind", kind="error")


def test_remind_alone_lists_yours(user):
    adi = user("Adi")
    adi.line("/remind 2h call grandma")
    adi.expect_text("I'll remind you")
    adi.line("/remind")
    listing = adi.expect_text("⏰ Your reminders")["text"]
    assert "call grandma" in listing


def test_due_while_away_comes_at_login(user):
    adi = user("Adi")
    adi.line("/remind 10m homework")
    adi.expect_text("I'll remind you")
    adi.close()
    user("Ben").line("/users")
    with state.lock:
        state.reminders[0]["due"] = time.time() - 1     # it came due while Adi was away
        reminders.deliver_due()
    assert len(state.reminders) == 1                     # kept: Adi isn't here
    back = user("Adi", action="login")
    back.expect_text("⏰ Reminder: homework")
    assert state.reminders == []


def test_reminders_survive_a_restart(user, tmp_path, monkeypatch):
    adi = user("Adi")
    adi.line("/remind 3h feed the cat")
    adi.expect_text("I'll remind you")
    path = tmp_path / "data.json"
    monkeypatch.setattr(config, "DATA_FILE", str(path))
    storage.save_data()
    assert json.loads(path.read_text(encoding="utf-8"))["reminders"][0]["text"] == "feed the cat"
    state.reminders = []
    assert storage.load_data()
    assert state.reminders[0]["login"] == "adi"
