"""📊 /hbstats (server admins only): Hashbrown's questions today, the server-wide cap used, the tokens the API
says it used, and a cost estimate from HASHBROWN_PRICE_IN / HASHBROWN_PRICE_OUT in config.py."""
import pytest

from chatserver import config, state

pytestmark = pytest.mark.integration


def ask(client):
    client.line("@hashbrown hi")
    client.expect(lambda m: m.get("type") == "chat" and m.get("name") == "Hashbrown")


def test_admins_see_questions_tokens_and_cost(user, fake_hashbrown, monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_PRICE_IN", 1.0)      # $ per million tokens
    monkeypatch.setattr(config, "HASHBROWN_PRICE_OUT", 10.0)
    adi = user("Adi")
    state.accounts["adi"]["admin"] = True
    ask(adi)
    state.hashbrown_last.clear()                                 # (past the per-person wait)
    ask(adi)
    adi.line("/hbstats")
    stats = adi.expect_text("🥔📊")["text"]
    assert "Questions today: 2" in stats
    assert f"Daily cap: 2/{config.HASHBROWN_DAILY_CAP}" in stats
    assert "240 tokens (200 in, 40 out)" in stats
    assert "$0.0006" in stats                                    # 200 x $1/M + 40 x $10/M


def test_only_server_admins(user):
    adi = user("Adi")
    adi.line("/hbstats")
    adi.expect_text("server admins", kind="error")


def test_a_new_day_starts_from_zero(user, fake_hashbrown):
    adi = user("Adi")
    state.accounts["adi"]["admin"] = True
    ask(adi)
    state.hashbrown_usage = {**state.hashbrown_usage, "day": "2000-01-01"}
    adi.line("/hbstats")
    assert "Questions today: 0" in adi.expect_text("🥔📊")["text"]
