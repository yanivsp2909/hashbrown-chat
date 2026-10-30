"""📰 Hashbrown's market news: when a company's price is MARKET_NEWS_MOVE_PERCENT up or down from the day's open,
Hashbrown posts one funny line in the Lobby (once per stock per day, at most MARKET_NEWS_PER_DAY a day, counted in
the server-wide AI cap). Without Hashbrown, nothing happens."""
import pytest

from chatserver import config, market, market_news, state

pytestmark = pytest.mark.integration


def crash(sym="FRY", to=50):
    market.ensure()
    state.stocks[sym]["open"] = 100
    old = market.prices()
    state.stocks[sym]["price"] = to
    with state.lock:
        market_news.check(old, market.prices())


def test_a_crash_makes_hashbrown_post_in_the_lobby(user, fake_hashbrown):
    adi = user("Adi")
    crash()
    news = adi.expect(lambda m: m.get("type") == "chat" and m.get("name") == "Hashbrown")
    assert news["text"].startswith("📰 ")
    asked = str(fake_hashbrown.requests[-1][1])
    assert "FRY" in asked and "down" in asked


def test_once_per_stock_per_day_and_a_daily_limit(user, fake_hashbrown, monkeypatch):
    monkeypatch.setattr(config, "MARKET_NEWS_PER_DAY", 2)
    adi = user("Adi")
    crash("FRY")
    adi.expect(lambda m: m.get("name") == "Hashbrown")
    crash("FRY", 40)
    crash("SPUD", 10)
    adi.expect(lambda m: m.get("name") == "Hashbrown")
    crash("SALT", 1)
    adi.line("/users")
    adi.expect_text("Online now")
    assert len(fake_hashbrown.requests) == 2


def test_small_moves_and_no_hashbrown_make_no_news(user):
    adi = user("Adi")
    crash("FRY", 95)
    crash("SPUD", 1)                 # a big move, but Hashbrown is off
    adi.line("/users")
    adi.expect_text("Online now")
    assert not [m for m in adi.messages if m.get("name") == "Hashbrown"]
