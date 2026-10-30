"""📊 The economy dashboard: {"type": "get_economy"} -> {"type": "economy"} with every token in the game, the public
fund, the richest players, the hottest stock today and the inflation over the week (from one total a day)."""
import pytest

from chatserver import economy, market, state

pytestmark = pytest.mark.integration


def test_the_dashboard_numbers(user):
    adi, ben = user("Adi"), user("Ben")
    state.accounts["ben"]["tokens"] = 900
    state.public_fund = 50
    market.ensure()
    state.stocks["SALT"]["open"], state.stocks["SALT"]["price"] = 20, 30
    state.supply_history = [["2026-10-24", 1000], ["2026-10-30", 1100]]
    adi.send({"type": "get_economy"})
    data = adi.expect(lambda m: m.get("type") == "economy")
    assert data["total"] == economy.total_supply() and data["fund"] == 50
    assert data["richest"][0] == {"name": "Ben", "tokens": 900}
    assert data["hottest"]["symbol"] == "SALT" and data["hottest"]["change"] == 50.0
    assert data["inflation_week"] == pytest.approx((economy.total_supply() - 1000) * 100 / 1000, abs=0.1)


def test_no_history_no_inflation_number(user):
    adi = user("Adi")
    adi.send({"type": "get_economy"})
    assert adi.expect(lambda m: m.get("type") == "economy")["inflation_week"] is None


def test_a_new_day_records_the_total():
    state.economy_day = "2000-01-01"
    with state.lock:
        economy.daily_tick()
    assert state.supply_history[-1][1] == economy.total_supply()
