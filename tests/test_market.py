"""📈 Stocks and 🧾 taxes. Four fake companies (FRY, SPUD, SALT, KTCH) whose prices take a random walk every
STOCK_TICK_SECONDS (limited to STOCK_MAX_MOVE_PERCENT a tick, never below STOCK_MIN_PRICE). /stocks, /buy FRY 5,
/sell FRY 5, /portfolio, with a TRADE_FEE_PERCENT fee. Each tick is ONE {"type": "market"} packet to everyone.
Fees and a tax on big casino wins go into the public fund, which pays the quest, question-of-the-day and drawing
prizes (only what it can't cover is made new)."""
import json
import random

import pytest

from chatserver import config, economy, fund, market, state, storage

pytestmark = pytest.mark.integration


def rich(key, tokens=5000):
    state.accounts[key]["tokens"] = tokens


def test_four_stocks_start_at_their_prices():
    market.ensure()
    assert set(state.stocks) == {"FRY", "SPUD", "SALT", "KTCH"}
    assert all(s["price"] == config.STOCKS[sym][2] for sym, s in state.stocks.items())


def test_a_tick_moves_prices_within_the_limits():
    market.ensure()
    random.seed(4)
    for _ in range(300):
        before = {sym: s["price"] for sym, s in state.stocks.items()}
        with state.lock:
            market.tick(broadcast=False)
        for sym, s in state.stocks.items():
            assert s["price"] >= config.STOCK_MIN_PRICE
            assert abs(s["price"] - before[sym]) <= max(1, before[sym] * config.STOCK_MAX_MOVE_PERCENT // 100)


def test_one_market_packet_per_tick_to_everyone(user):
    adi, old = user("Adi"), user("Old")
    market.ensure()
    with state.lock:
        market.tick()
    for client in (adi, old):
        packet = client.expect(lambda m: m.get("type") == "market")
        assert set(packet["prices"]) >= {"FRY", "SPUD", "SALT", "KTCH"}


def test_buy_and_sell_with_a_fee_into_the_fund(user):
    adi = user("Adi")
    rich("adi")
    market.ensure()
    state.stocks["FRY"]["price"] = 100
    adi.line("/buy FRY 5")
    adi.expect_text("You bought 5 FRY")
    fee = max(1, 500 * config.TRADE_FEE_PERCENT // 100)
    assert state.accounts["adi"]["tokens"] == 5000 - 500 - fee
    assert state.accounts["adi"]["portfolio"] == {"FRY": 5}
    assert state.public_fund == fee
    state.stocks["FRY"]["price"] = 120
    adi.line("/sell FRY 2")
    adi.expect_text("You sold 2 FRY")
    assert state.accounts["adi"]["portfolio"] == {"FRY": 3}
    adi.line("/portfolio")
    shown = adi.expect_text("📈 Your portfolio")["text"]
    assert "FRY" in shown and "3" in shown


@pytest.mark.parametrize("line, error", [
    ("/buy FRY 0", "Use: /buy"), ("/buy NOPE 2", "No stock"), ("/buy FRY 5000", "can't afford"),
    ("/sell FRY 1", "only have 0"),
])
def test_trading_mistakes(user, line, error):
    adi = user("Adi")
    market.ensure()
    adi.line(line)
    adi.expect_text(error, kind="error")


def test_buy_still_buys_badges_from_the_shop(user):
    adi = user("Adi")
    rich("adi")
    badge = next(iter(config.SHOP))
    adi.line(f"/buy {badge}")
    adi.expect(lambda m: badge in str(m.get("text", "")) and m.get("kind") != "error")
    assert badge in state.accounts["adi"]["badges"]


def test_stocks_list_prices_and_changes(user):
    adi = user("Adi")
    market.ensure()
    adi.line("/stocks")
    listing = adi.expect_text("📈 Stocks")["text"]
    for sym in ("FRY", "SPUD", "SALT", "KTCH"):
        assert sym in listing


def test_a_big_casino_win_is_taxed_into_the_fund(user, monkeypatch):
    adi = user("Adi")
    rich("adi", 10000)
    monkeypatch.setattr(random, "choices", lambda symbols, k: ["🍒"] * 3)   # x10
    adi.line("/slots 100")
    won = adi.expect_text("You won")["text"]
    tax = 900 * config.CASINO_TAX_PERCENT // 100
    assert state.public_fund == tax and f"{tax} 🪙 tax" in won


def test_small_wins_arent_taxed(user, monkeypatch):
    adi = user("Adi")
    rich("adi", 1000)
    monkeypatch.setattr(random, "choices", lambda symbols, k: ["🍒", "🍒", "🍋"])   # x1.5
    adi.line("/slots 10")
    adi.expect_text("You won")
    assert state.public_fund == 0


def test_prizes_come_from_the_fund_first():
    state.accounts["zed"] = storage.new_account("Zed", "s", "h")
    state.public_fund = 20
    before = state.accounts["zed"]["tokens"]
    from_fund = fund.pay_prize("zed", 30)
    assert from_fund == 20 and state.public_fund == 0 and state.accounts["zed"]["tokens"] == before + 30


def test_the_market_and_fund_are_saved(tmp_path, monkeypatch):
    market.ensure()
    state.stocks["SALT"]["price"] = 77
    state.public_fund = 123
    path = tmp_path / "data.json"
    monkeypatch.setattr(config, "DATA_FILE", str(path))
    storage.save_data()
    saved = json.loads(path.read_text(encoding="utf-8"))["economy"]
    assert saved["fund"] == 123 and saved["stocks"]["SALT"]["price"] == 77
    state.public_fund, state.stocks = 0, {}
    assert storage.load_data()
    assert state.public_fund == 123 and state.stocks["SALT"]["price"] == 77
    assert economy is not None


def test_the_website_gets_the_market_with_charts_and_your_shares(user):
    adi = user("Adi")
    rich("adi")
    market.ensure()
    with state.lock:
        market.tick(broadcast=False)
    adi.line("/buy SPUD 3")
    adi.expect_text("You bought 3 SPUD")
    adi.send({"type": "get_market"})
    info = adi.expect(lambda m: m.get("type") == "market_info")
    assert info["portfolio"] == {"SPUD": 3} and len(info["stocks"]["FRY"]["history"]) == 1
    assert info["stocks"]["KTCH"]["icon"] == "🥫" and info["fee_percent"] == config.TRADE_FEE_PERCENT
