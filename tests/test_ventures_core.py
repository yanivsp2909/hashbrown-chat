"""🏢 Hashbrown Ventures, the pure parts: the cap table math, the daily simulation and the actions.
(No server here: these are plain functions, so they are quick to test and the balance simulation can run them.)"""
import random

import pytest

from chatserver import cap_table, config, ventures_actions, ventures_sim, ventures_store

TOTAL = cap_table.TOTAL


def company(**changes):
    """A fresh SaaS company with one founder, plus any changes."""
    co = ventures_store.new_company("c1", "Spudly", "spudly", "saas", "adi", tick=0)
    return {**co, **changes}


# ---------------------------------------------------------------- the cap table

def test_a_new_company_belongs_to_its_founder():
    co = company()
    assert co["cap"] == {"p:adi": TOTAL}
    assert co["roles"] == {"adi": "ceo"}


def test_dilution_keeps_the_total_and_shrinks_everyone_alike():
    cap = {"p:adi": 6000, "p:ben": 4000}
    after = cap_table.dilute(cap, "i:maya", 2000)
    assert after == {"p:adi": 4800, "p:ben": 3200, "i:maya": 2000}
    assert sum(after.values()) == TOTAL
    assert cap == {"p:adi": 6000, "p:ben": 4000}   # the old table is untouched


def test_dilution_adds_to_a_holder_who_already_owns_some():
    after = cap_table.dilute({"p:adi": 9000, "i:maya": 1000}, "i:maya", 1000)
    assert after == {"p:adi": 8100, "i:maya": 1900}


def test_rounding_leftovers_go_to_the_biggest_holder():
    after = cap_table.normalize({"a": 3333, "b": 3333, "c": 3333})
    assert sum(after.values()) == TOTAL
    assert sorted(after.values()) == [3333, 3333, 3334]


def test_moving_equity_never_takes_more_than_the_giver_has():
    after = cap_table.move({"p:adi": 9000, "p:ben": 1000}, "p:ben", "p:cat", 5000)
    assert after == {"p:adi": 9000, "p:cat": 1000}


def test_a_grant_vests_a_quarter_at_once_then_day_by_day():
    grant = {"bp": 1000, "tick": 10}
    assert cap_table.vested(grant, 10) == 250
    assert cap_table.vested(grant, 10 + config.VEST_TICKS // 2) == 625
    assert cap_table.vested(grant, 10 + config.VEST_TICKS * 3) == 1000


def test_percent_text():
    assert cap_table.percent_text(1250) == "12.5%"
    assert cap_table.percent_text(10000) == "100%"


# ---------------------------------------------------------------- the numbers

def test_revenue_is_customers_times_the_sector_price():
    co = company(customers=150.0)
    assert ventures_sim.revenue(co) == 150 * config.SECTORS["saas"]["price"]


def test_burn_counts_staff_players_office_and_cost_of_revenue():
    co = company(staff={"engineer": 2, "sales": 1, "marketer": 0}, customers=100.0)
    expected = (3 * config.SALARY + 2 * config.FOUNDER_PAY + config.STAGE_NUMBERS["idea"]["office"]
                + 100 * config.SECTORS["saas"]["price"] * config.SECTORS["saas"]["cost_of_revenue"])
    assert ventures_sim.burn(co, players=2) == pytest.approx(expected)


def test_a_cfo_cuts_the_burn():
    plain, with_cfo = company(), company(roles={"adi": "ceo", "ben": "cfo"})
    assert ventures_sim.burn(with_cfo, 2) == pytest.approx(ventures_sim.burn(plain, 2) * (1 - config.CFO_BURN_CUT))


def test_runway_is_none_when_profitable():
    assert ventures_sim.runway(company(cash=100_000, customers=10_000.0), players=1) is None
    assert ventures_sim.runway(company(cash=70_000), players=1) == 10   # $7K a day, $70K left


def test_milestones_for_the_next_round():
    co = company(stage="preseed", quality=31.0, customers=500.0, stage_ticks=config.ROUND_MIN_TICKS)
    rows = ventures_sim.milestones(co)
    assert [r["what"] for r in rows] == ["MRR", "quality", "ticks"]
    assert [r["ok"] for r in rows] == [False, True, True]   # MRR $5K of $10K
    assert not ventures_sim.ready(co)
    assert ventures_sim.ready({**co, "customers": 1000.0})


def test_valuation_never_drops_below_most_of_the_last_round():
    co = company(last_post=10_000_000)
    assert ventures_sim.valuation(co) == pytest.approx(8_000_000)
    rich = company(customers=300_000.0, quality=80.0, hype=60.0, reputation=70.0)
    assert ventures_sim.valuation(rich) > 1_000_000_000


# ---------------------------------------------------------------- the daily tick

def test_a_day_burns_cash_grows_quality_and_ages_the_stage():
    co = company(staff={"engineer": 2, "sales": 0, "marketer": 0}, quality=30.0, acted=True)
    new, lines = ventures_sim.next_day(co, random.Random(1), players=1)
    assert new["quality"] > co["quality"]
    assert new["cash"] < co["cash"]
    assert new["stage_ticks"] == 1 and new["age"] == 1
    assert new["idle"] == 0 and new["acted"] is False
    assert co["cash"] == config.START_CASH   # the old record is untouched
    assert any("Cash" in line for line in lines)


def test_customers_come_when_the_product_is_good():
    co = company(quality=60.0, hype=50.0)
    new, _ = ventures_sim.next_day(co, random.Random(2), players=1)
    assert new["customers"] > 0


def test_no_action_for_days_makes_hype_fall_faster():
    busy = company(hype=60.0, acted=True)
    lazy = company(hype=60.0, idle=config.IDLE_TICKS)
    assert ventures_sim.next_day(lazy, random.Random(3), 1)[0]["hype"] < ventures_sim.next_day(busy, random.Random(3), 1)[0]["hype"]


def test_out_of_cash_means_on_fumes_then_dead():
    broke = company(cash=1_000)
    day1, lines1 = ventures_sim.next_day(broke, random.Random(4), players=1)
    assert day1["fumes"] and day1["status"] == "alive"
    assert any("fumes" in line for line in lines1)
    day2, _ = ventures_sim.next_day(day1, random.Random(4), players=1)
    assert day2["status"] == "dead"
    assert day2["cause"]


def test_money_back_above_zero_ends_the_fumes():
    co = company(cash=-500, fumes=True)
    back = {**co, "cash": 1_000_000}
    new, _ = ventures_sim.next_day(back, random.Random(5), players=1)
    assert new["status"] == "alive" and not new["fumes"]


def test_the_peak_valuation_is_remembered():
    co = company(customers=5_000.0, quality=50.0)
    new, _ = ventures_sim.next_day(co, random.Random(6), players=1)
    assert new["peak"] == pytest.approx(max(co["peak"], new["valuation"]))


# ---------------------------------------------------------------- actions

def test_build_spends_an_action_point_and_raises_quality():
    co = company(ap=3)
    new, text = ventures_actions.apply(co, "build", "")
    assert new["ap"] == 2 and new["quality"] > co["quality"] and new["acted"]
    assert "quality" in text


def test_a_cto_builds_faster():
    plain = ventures_actions.apply(company(ap=3), "build", "")[0]["quality"]
    cto = ventures_actions.apply(company(ap=3, roles={"adi": "ceo", "ben": "cto"}), "build", "")[0]["quality"]
    assert cto > plain


def test_no_action_points_left():
    with pytest.raises(ventures_actions.ActionError, match="action point"):
        ventures_actions.apply(company(ap=0), "build", "")


def test_hiring_costs_cash_and_respects_the_staff_limit():
    co = company(ap=3)
    new, _ = ventures_actions.apply(co, "hire", "engineer")
    assert new["staff"]["engineer"] == 1 and new["cash"] == co["cash"] - config.HIRE_COST
    full = company(ap=3, staff={"engineer": 2, "sales": 0, "marketer": 0})
    with pytest.raises(ventures_actions.ActionError, match="at most"):
        ventures_actions.apply(full, "hire", "sales")


def test_hire_needs_a_kind():
    with pytest.raises(ventures_actions.ActionError, match="engineer"):
        ventures_actions.apply(company(ap=3), "hire", "astronaut")


def test_not_enough_cash():
    with pytest.raises(ventures_actions.ActionError, match="cash"):
        ventures_actions.apply(company(ap=3, cash=100), "marketing", "")


def test_marketing_raises_hype_and_sales_brings_customers():
    co = company(ap=3)
    assert ventures_actions.apply(co, "marketing", "")[0]["hype"] > co["hype"]
    assert ventures_actions.apply(co, "sales", "")[0]["customers"] > co["customers"]


def test_layoff_saves_salaries_but_costs_reputation():
    co = company(ap=3, staff={"engineer": 2, "sales": 0, "marketer": 0})
    new, _ = ventures_actions.apply(co, "layoff", "engineer 1")
    assert new["staff"]["engineer"] == 1 and new["reputation"] < co["reputation"]
    assert new["cash"] == co["cash"] - config.SEVERANCE


def test_pivot_once_per_stage_and_it_can_change_sector():
    co = company(ap=config.PIVOT_AP, quality=40.0, customers=1000.0)
    new, _ = ventures_actions.apply(co, "pivot", "ai")
    assert new["sector"] == "ai" and new["quality"] == pytest.approx(20.0) and new["ap"] == 0
    with pytest.raises(ventures_actions.ActionError, match="once"):
        ventures_actions.apply({**new, "ap": config.PIVOT_AP}, "pivot", "")


def test_unknown_action():
    with pytest.raises(ventures_actions.ActionError, match="actions"):
        ventures_actions.apply(company(ap=3), "teleport", "")


def test_the_action_list_says_what_is_possible():
    rows = ventures_actions.menu(company(ap=1))
    by_name = {r["name"]: r for r in rows}
    assert by_name["build"]["ok"] and not by_name["pivot"]["ok"]
    assert "action points" in by_name["pivot"]["why"]


def test_an_idle_company_loses_customers_faster():
    busy = company(customers=1000.0, quality=50.0, acted=True)
    lazy = company(customers=1000.0, quality=50.0, idle=config.IDLE_TICKS)
    assert ventures_sim.next_day(lazy, random.Random(8), 1)[0]["customers"] < ventures_sim.next_day(busy, random.Random(8), 1)[0]["customers"]


def test_money_rounds_up_to_the_next_unit():
    from chatserver.ventures_text import money
    assert money(999_960) == "$1M" and money(12_340) == "$12.3K" and money(-5_000) == "-$5K" and money(950) == "$950"


def test_the_report_warns_about_a_short_runway():
    co = company(cash=20_000)
    _, lines = ventures_sim.next_day(co, random.Random(9), players=1)
    assert any("days of cash left" in line for line in lines)


def test_a_day_has_six_action_points_and_friends_add_up_to_nine():
    assert config.AP_BASE == 6 and config.AP_MAX == 9
    assert company()["ap"] == config.AP_BASE
