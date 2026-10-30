"""Hashbrown, the AI member. Always against a fake local Foundry server, never the real one."""
import pytest

import server

pytestmark = pytest.mark.integration


def is_hashbrown_answer(msg):
    return msg.get("type") == "chat" and msg.get("name") == "Hashbrown"


def ask_and_wait_for_answer(asker):
    asker.sync()  # skip answers to other people's questions that this person already saw
    asker.line("@hashbrown hi")
    asker.expect(is_hashbrown_answer)


# ---------------------------------------------------------------- server-wide daily cap

def test_daily_cap_stops_questions_for_everyone(user, fake_hashbrown, monkeypatch):
    monkeypatch.setattr(server, "HASHBROWN_DAILY_CAP", 2)
    adi, ben, cara = user("Adi"), user("Ben"), user("Cara")
    ask_and_wait_for_answer(adi)
    ask_and_wait_for_answer(ben)
    cara.line("@hashbrown hi")
    cara.expect_text("questions today", kind="error")
    assert server.accounts["cara"]["tokens"] == server.START_TOKENS  # not charged
    assert len(fake_hashbrown.requests) == 2  # the AI wasn't called a third time


def test_failed_questions_do_not_count_toward_the_daily_cap(user, fake_hashbrown, monkeypatch):
    monkeypatch.setattr(server, "HASHBROWN_DAILY_CAP", 1)
    adi, ben = user("Adi"), user("Ben")
    fake_hashbrown.status = 500
    adi.line("@hashbrown hi")
    adi.expect_text("refunded")
    fake_hashbrown.status = 200
    ask_and_wait_for_answer(ben)


def test_daily_cap_starts_again_the_next_day(user, fake_hashbrown, monkeypatch):
    monkeypatch.setattr(server, "HASHBROWN_DAILY_CAP", 1)
    adi, ben = user("Adi"), user("Ben")
    ask_and_wait_for_answer(adi)
    monkeypatch.setattr(server, "today", lambda: "2099-01-01")
    ask_and_wait_for_answer(ben)
