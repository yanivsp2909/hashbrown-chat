"""🏭 Each sector's own mechanics (ventures_sectors.py, pure), market events and the news feed."""
import random

import pytest

from chatserver import config, state, ventures_actions, ventures_events, ventures_news, ventures_sectors, ventures_sim, ventures_store
from test_ventures_company import found, grown_up


def company(sector, **changes):
    co = ventures_store.new_company("c1", "Labby", "labby", sector, "adi", tick=0)
    return {**co, "ap": 6, "cash": 10_000_000, **changes}


def sector_state(co, **changes):
    return ventures_sectors.with_state(co, **changes)


def act(co, name, args="", seed=1, tick=0):
    return ventures_actions.apply(co, name, args, random.Random(seed), tick)


# ---------------------------------------------------------------- 🤖 AI lab

def test_an_ai_lab_buys_compute_trains_and_releases():
    co, _ = act(company("ai"), "compute", "40")
    assert ventures_sectors.state(co)["compute"] == 40 and co["cash"] == 10_000_000 - 40 * config.COMPUTE_PRICE
    co, text = act(co, "train")
    assert "Training model 1" in text and ventures_sectors.state(co)["training"]["left"] == config.TRAIN_TICKS
    for _ in range(config.TRAIN_TICKS):
        co, lines, _ = ventures_sectors.day({**co, "quality": 60.0}, random.Random(2), {"tick": 1})
    assert ventures_sectors.state(co)["models"][0]["score"] > 0 and any("Training done" in l for l in lines)
    co, text = act({**co, "ap": 6}, "release")
    assert ventures_sectors.state(co)["models"][0]["released"] and "Released" in text


def test_training_needs_compute_and_serving_eats_it():
    with pytest.raises(ventures_actions.ActionError, match="compute"):
        act(company("ai"), "train")
    co = sector_state(company("ai", customers=500.0), compute=2)
    hungry, lines, _ = ventures_sectors.day(co, random.Random(3), {"tick": 1})
    assert ventures_sectors.state(hungry)["compute"] == 0 and hungry["customers"] < 500 and "Out of compute" in lines[0]


def test_the_spud_bench_ranks_labs_and_boosts_the_best():
    co = sector_state(company("ai"), models=[{"name": "Labby 1", "score": 99.0, "safety": 40, "released": True}])
    rows, boost = ventures_sectors.bench([co], tick=0)
    assert rows[0]["lab"] == "Labby" and boost["c1"] == 1.5


# ---------------------------------------------------------------- 🛡️ cyber, 📱 hardware, 💻 SaaS, 🎮 games

def test_cyber_lines_and_security():
    co, _ = act(company("cyber"), "launch", "agent")
    assert ventures_sectors.state(co)["lines"]["agent"] == 20
    with pytest.raises(ventures_actions.ActionError, match="already launched"):
        act(co, "launch", "agent")
    co, _ = act(co, "audit")
    assert ventures_sectors.state(co)["security"] == config.CYBER_SECURITY_START + 15


def test_a_breach_hurts_a_cyber_company_with_weak_security():
    class Unlucky(random.Random):
        def random(self):
            return 0.0
    co = sector_state(company("cyber", customers=10.0), security=0)
    hit, lines, news = ventures_sectors.day(co, Unlucky(), {"tick": 1})
    assert hit["customers"] == 8.0 and hit["reputation"] == config.START_REPUTATION - 20 and news


def test_hardware_sells_only_what_is_in_stock():
    co, _ = act(company("hardware", customers=50.0), "manufacture", "30")
    assert ventures_sectors.state(co)["batches"][0]["arrive"] == config.MANUFACTURE_TICKS
    co, _, _ = ventures_sectors.day(co, random.Random(1), {"tick": config.MANUFACTURE_TICKS})
    s = ventures_sectors.state(co)
    assert s["sold"] == 30 and s["stock"] == 0 and s["unmet"] == 20
    assert ventures_sim.revenue(co) == 30 * (config.DEVICES["phone"][0] - config.DEVICES["phone"][1])


def test_a_keynote_waits_between_shows():
    co, _ = act(company("hardware"), "keynote", tick=5)
    with pytest.raises(ventures_actions.ActionError, match="keynote"):
        act({**co, "ap": 6}, "keynote", tick=6)


def test_saas_price_changes_revenue_and_churn():
    co, _ = act(company("saas", customers=100.0), "priceup")
    assert ventures_sim.revenue(co) == pytest.approx(100 * config.SECTORS["saas"]["price"] * config.SAAS_PRICE_STEP)
    assert ventures_sectors.effects(co, {})["churn"] > 1


def test_a_game_launches_only_when_done():
    with pytest.raises(ventures_actions.ActionError, match="100%"):
        act(company("game"), "launch")
    ready = sector_state(company("game", hype=80.0), project={"progress": 100, "quality": 95.0, "number": 1})
    launched, text = act(ready, "launch", seed=4)
    assert launched["customers"] > 0 and launched["cash"] > ready["cash"] and "launched" in text
    assert ventures_sectors.state(launched)["project"]["number"] == 2


def test_the_menu_has_the_sectors_own_actions():
    names = {r["name"] for r in ventures_actions.menu(company("ai"))}
    assert {"build", "compute", "train", "release", "safety"} <= names


def test_a_pivot_starts_the_new_sectors_numbers_fresh():
    co, _ = act(sector_state(company("ai"), compute=99), "pivot", "game")
    assert co["sector"] == "game" and ventures_sectors.state(co)["project"]["progress"] == 0


# ---------------------------------------------------------------- market events and news (on the server)

@pytest.mark.integration
def test_a_template_event_hits_and_makes_news(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    with state.lock:
        ventures_events.apply_event({"kind": "demand_up", "direction": "up", "sector": "saas", "company": "",
                                     "strength": 2, "days": 3, "headline": None, "text": ""}, random.Random(1))
    adi.expect_text("📰 🌪️")
    events = ventures_events.active()
    assert events[0]["demand"] == 1.25 and events[0]["until"] == 3
    assert ventures_news.feed()[0]["kind"] == "event"
    fx = ventures_sectors.effects(ventures_store.find("Spudly"), {"events": events})
    assert fx["demand"] == pytest.approx(1.25)


@pytest.mark.integration
def test_the_ai_event_is_checked_and_its_numbers_are_the_servers(user, fake_hashbrown):
    import json
    fake_hashbrown.answers = [json.dumps({"kind": "viral", "direction": "up", "sector": "all", "company": "SPUDLY",
                                          "strength": 99, "days": 77, "headline": "Spudly is everywhere", "text": "Wow."})]
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    with state.lock:
        ventures_events.start(random.Random(1))
    adi.expect_text("Spudly is everywhere", timeout=10)
    assert ventures_store.find("Spudly")["hype"] == config.START_HYPE + 30   # strength kept at 3


@pytest.mark.integration
def test_founding_and_sector_actions_by_command(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi, "Labby", "ai")
    assert ventures_news.feed()[0]["kind"] == "founded"
    adi.line("/company compute 5")
    adi.expect_text("Bought 5 compute")
    adi.line("/company train")
    adi.expect_text(f"needs {config.TRAIN_COMPUTE} compute", kind="error")


@pytest.mark.integration
def test_events_come_at_their_hours(user, monkeypatch):
    from datetime import datetime
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    with state.lock:
        assert not ventures_events.maybe_run(datetime(2026, 11, 2, 11, 0))
        assert ventures_events.maybe_run(datetime(2026, 11, 2, 12, 5))
        assert not ventures_events.maybe_run(datetime(2026, 11, 2, 12, 30))
        assert ventures_events.maybe_run(datetime(2026, 11, 2, 21, 0))   # (16 and 20 together, one event)


def test_a_template_headline_says_the_real_effect():
    event = {"kind": "market_mood", "direction": "down", "sector": "all", "company": "", "strength": 3, "days": 5}
    fields, _ = ventures_events.effect(event)
    assert fields == {"mood": 0.8} and "-20%" in ventures_events.template_headline(event, None)
    outage = {"kind": "outage", "direction": "up", "sector": "all", "company": "c1", "strength": 2, "days": 1}
    assert "6%" in ventures_events.template_headline(outage, {"name": "Spudly"})


@pytest.mark.integration
def test_events_slots_and_prices_survive_a_restart(user):
    from chatserver import storage
    adi = user("Adi")
    grown_up("adi")
    found(adi, "Labby", "ai")
    with state.lock:
        ventures_events.apply_event({"kind": "compute_price", "direction": "up", "sector": "ai", "company": "",
                                     "strength": 3, "days": 3, "headline": None, "text": ""}, random.Random(1))
        ventures_store.set_field("event_slots", {"day": "2026-11-02", "done": [12, 16]})
        assert ventures_sectors.compute_price() == int(config.COMPUTE_PRICE * 1.4)
        storage.save_data()
        state.ventures = {}
        assert storage.load_data()
        assert ventures_sectors.compute_price() == int(config.COMPUTE_PRICE * 1.4)
        assert state.ventures["event_slots"] == {"day": "2026-11-02", "done": [12, 16]}


def test_a_cyber_line_button_with_nothing_to_pick_is_off():
    from chatserver import ventures_view
    co = sector_state(company("cyber"), lines={k: 30 for k in config.CYBER_LINES})
    rows = {r["name"]: r for r in ventures_view.actions(co)}
    assert not rows["launch"]["ok"] and "launched" in rows["launch"]["why"] and rows["improve"]["ok"]


def test_pivoting_back_starts_fresh():
    co = sector_state(company("ai"), compute=99)
    there, _ = act(co, "pivot", "game")
    back = {**there, "pivoted": "", "ap": 6}
    again, _ = act(back, "pivot", "ai")
    assert ventures_sectors.state(again)["compute"] == 0
