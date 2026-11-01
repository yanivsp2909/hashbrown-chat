"""
🏢 Hashbrown Ventures on a real server: founding a company (it is a private group), the team with roles and
equity, the daily actions, the daily tick with its report, death and the graveyard, and the guards that keep
company money (game dollars) away from the group bank (tokens).
"""
import json
import random
import sqlite3
import time

import pytest

from chatserver import background, config, state, storage, ventures_store, ventures_tick

pytestmark = pytest.mark.integration


def grown_up(*keys, tokens=1000):
    """Accounts made two days ago, with some tokens."""
    with state.lock:
        for key in keys:
            state.accounts[key]["created"] = time.time() - 48 * 3600
            state.accounts[key]["tokens"] = tokens


def found(client, name="Spudly", sector="saas"):
    client.line(f"/company found {name} {sector}")
    client.expect_text(f"Founded {name}")
    return ventures_store.find(name)


def tick():
    with state.lock:
        ventures_tick.run_tick(random.Random(7))


def company(name="Spudly"):
    with state.lock:
        return ventures_store.find(name)


def team(user):
    """Adi founds Spudly; Ben is invited as CTO with 10% and joins."""
    adi, ben = user("Adi"), user("Ben")
    grown_up("adi", "ben")
    found(adi)
    adi.line("/company invite Ben cto 10")
    ben.expect(lambda m: isinstance(m.get("company_invite"), dict))
    ben.line("/join Spudly")
    ben.expect_text("joined Spudly")
    return adi, ben


# ---------------------------------------------------------------- founding

def test_founding_makes_a_private_company_group_and_takes_the_fee(user):
    adi = user("Adi")
    grown_up("adi")
    fund_before = state.public_fund
    co = found(adi)
    group = state.groups["spudly"]
    assert group["private"] and group["company"] == co["id"] and group["owner"] == "adi"
    assert co["sector"] == "saas" and co["stage"] == "idea" and co["cash"] == config.START_CASH
    assert state.accounts["adi"]["tokens"] == 1000 - config.FOUND_COST
    assert state.public_fund == fund_before + config.FOUND_COST
    assert adi.expect(lambda m: m.get("type") == "history")   # moved into the company chat


def test_founding_rules(user):
    adi = user("Adi")
    adi.line("/company found Spudly saas")
    adi.expect_text("24 hours old", kind="error")
    grown_up("adi", tokens=50)
    adi.line("/company found Spudly saas")
    adi.expect_text(f"costs {config.FOUND_COST}", kind="error")
    grown_up("adi")
    adi.line("/company found Spudly rockets")
    adi.expect_text("Sectors:", kind="error")
    adi.line("/company found Lobby saas")
    adi.expect_text("❌", kind="error")
    found(adi)
    adi.line("/company found Second ai")
    adi.expect_text("One company at a time", kind="error")


def test_a_company_name_cant_be_an_existing_group(user):
    adi = user("Adi")
    grown_up("adi")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    adi.line("/company found Potatoes saas")
    adi.expect_text("taken", kind="error")


def test_status_info_and_actions(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi")
    found(adi)
    adi.line("/company")
    status = adi.expect_text("Cash")["text"]
    assert "Spudly" in status and "action points" in status
    adi.line("/company actions")
    assert "build" in adi.expect_text("⚡")["text"]
    cat.line("/company info Spudly")
    public = cat.expect_text("Spudly")["text"]
    assert "Adi" in public and "Cash" not in public   # outsiders don't see the bank
    cat.line("/company")
    cat.expect_text("not in a company")


# ---------------------------------------------------------------- actions

def test_an_action_spends_points_and_is_told_to_the_company(user):
    adi, ben = team(user)
    ben.line("/company build")
    adi.expect_text("Ben:")
    co = company()
    assert co["ap"] == config.AP_BASE + 1 - 1   # Ben was seen today (+1), then spent one
    assert co["quality"] > config.START_QUALITY and co["acted"]


def test_no_points_left(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    for _ in range(config.AP_BASE):
        adi.line("/company build")
        adi.expect_text("quality")
    adi.line("/company build")
    adi.expect_text("action points", kind="error")


def test_actions_work_from_any_room(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    adi.line("/lobby")
    adi.line("/company hire engineer")
    adi.expect_text("Hired 1 engineer")
    assert company()["staff"]["engineer"] == 1


# ---------------------------------------------------------------- the team

def test_an_invite_with_a_role_and_equity(user):
    adi, ben = team(user)
    co = company()
    assert co["roles"] == {"adi": "ceo", "ben": "cto"}
    assert co["cap"] == {"p:adi": 9000, "p:ben": 1000}
    assert "ben" in state.groups["spudly"]["admins"]   # a C-level seat is a group admin


def test_the_invite_card_tells_old_apps_what_to_do(user):
    adi, ben = user("Adi"), user("Ben")
    grown_up("adi", "ben")
    found(adi)
    adi.line("/company invite Ben engineer")
    card = ben.expect(lambda m: isinstance(m.get("company_invite"), dict))
    assert "/join Spudly" in card["text"] and card["company_invite"]["role"] == "engineer"


def test_one_company_at_a_time_even_by_invite(user):
    adi, ben = user("Adi"), user("Ben")
    grown_up("adi", "ben")
    found(adi)
    found(ben, "Fryware", "ai")
    adi.line("/company invite Ben engineer")
    ben.expect(lambda m: isinstance(m.get("company_invite"), dict))
    ben.line("/join Spudly")
    ben.expect_text("One company at a time", kind="error")


def test_only_invites_get_into_a_company(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    found(adi)
    cat.line("/join Spudly")
    cat.expect_text("ask its CEO", kind="error")
    assert "cat" not in state.groups["spudly"]["requests"]


def test_only_the_ceo_hands_out_equity_and_c_level_seats(user):
    adi, ben = team(user)
    cat = user("Cat")
    grown_up("cat")
    ben.line("/company invite Cat cfo")
    ben.expect_text("Only the CEO", kind="error")
    ben.line("/company invite Cat engineer 5")
    ben.expect_text("Only the CEO", kind="error")
    adi.line("/company invite Cat cto")
    adi.expect_text("already has a CTO", kind="error")


def test_roles_and_grants(user):
    adi, ben = team(user)
    adi.line("/company role Ben cfo")
    adi.expect_text("CFO")
    adi.line("/company grant Ben 5")
    adi.expect_text("5%")
    co = company()
    assert co["roles"]["ben"] == "cfo" and co["cap"] == {"p:adi": 8500, "p:ben": 1500}


def test_leaving_keeps_only_the_vested_part(user):
    adi, ben = team(user)
    ben.line("/company leave")
    ben.expect_text("You left Spudly")
    co = company()
    assert "ben" not in co["roles"] and "ben" not in state.groups["spudly"]["members"]
    assert co["cap"] == {"p:adi": 9750, "p:ben": 250}   # 25% of the 10% vests at once


def test_the_ceo_can_fire_and_hand_over(user):
    adi, ben = team(user)
    adi.line("/company ceo Ben")
    adi.expect_text("Ben is the CEO")
    group = state.groups["spudly"]
    assert group["owner"] == "ben" and company()["roles"] == {"ben": "ceo", "adi": "cto"}
    ben.line("/company fire Adi")
    adi.expect_text("let you go")
    assert "adi" not in state.groups["spudly"]["members"]


def test_shutdown_needs_the_name_and_goes_to_the_graveyard(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    adi.line("/company shutdown")
    adi.expect_text("type its name", kind="error")
    adi.line("/company shutdown Spudly")
    adi.expect_text("shut down")
    assert company()["status"] == "shutdown"
    assert state.ventures["graveyard"][-1]["name"] == "Spudly"
    adi.line("/company found Again saas")
    adi.expect_text("wait", kind="error")   # the cooldown


# ---------------------------------------------------------------- guards: company money is not the group bank

@pytest.mark.parametrize("line", ["/donate 10", "/upgrade income", "/war potatoes", "/promote Ben", "/kick Ben",
                                  "/disband"])
def test_bank_and_admin_commands_are_off_in_a_company(user, line):
    adi, ben = team(user)
    adi.line("/join Spudly")
    adi.line(line)
    adi.expect_text("🏢", kind="error")
    assert state.groups["spudly"]["bank"] == 0


def test_no_group_income_and_no_group_stock_for_a_company(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    background.income_tick()
    with state.lock:
        from chatserver import group_stocks
        group_stocks.tick()
    assert state.groups["spudly"]["bank"] == 0
    assert "#spudly" not in state.stocks


def test_a_company_doesnt_count_as_an_owned_group(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    for name in ("One", "Two"):
        adi.line(f"/create {name}")
        adi.expect_text("Created")


def test_slash_leave_in_a_company_is_company_leave(user):
    adi, ben = team(user)
    ben.line("/join Spudly")
    ben.line("/leave")
    ben.expect_text("You left Spudly")
    assert company()["cap"]["p:ben"] == 250


# ---------------------------------------------------------------- the daily tick

def test_the_tick_reports_refills_points_and_saves_a_chart_row(user):
    adi = user("Adi", features=["ventures"])
    grown_up("adi")
    found(adi)
    adi.line("/company build")
    adi.expect_text("quality")
    tick()
    report = adi.expect(lambda m: m.get("type") == "chat" and "📊 Day 1" in m.get("text", ""))
    assert "Cash" in report["text"]
    event = adi.expect(lambda m: m.get("type") == "company_event" and m.get("kind") == "report")
    assert event["company"] == company()["id"]
    co = company()
    assert co["ap"] == config.AP_BASE and co["age"] == 1 and state.ventures["tick"] == 1
    rows = sqlite3.connect(config.HISTORY_DB).execute("SELECT company, age, cash FROM venture_days").fetchall()
    assert rows == [(co["id"], 1, co["cash"])]


def test_a_broke_company_is_on_fumes_then_dies(user):
    adi = user("Adi")
    grown_up("adi")
    co = found(adi)
    with state.lock:
        ventures_store.update(co["id"], cash=100)
    tick()
    adi.expect_text("on fumes")
    tick()
    adi.expect_text("died")
    dead = company()
    assert dead["status"] == "dead"
    grave = state.ventures["graveyard"][-1]
    assert grave["name"] == "Spudly" and grave["cause"] and grave["founders"] == ["Adi"]
    adi.line("/ventures graveyard")
    adi.expect_text("Spudly")
    adi.line("/company build")
    adi.expect_text("not in a company", kind="error")


def test_the_tick_runs_once_a_day_after_the_hour(user, monkeypatch):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    from datetime import datetime
    monkeypatch.setattr(ventures_tick, "israel_now", lambda: datetime(2026, 11, 2, config.VENTURES_TICK_HOUR - 1, 0))
    with state.lock:
        ventures_tick.maybe_run()
    assert state.ventures["tick"] == 0
    monkeypatch.setattr(ventures_tick, "israel_now", lambda: datetime(2026, 11, 2, config.VENTURES_TICK_HOUR, 5))
    with state.lock:
        ventures_tick.maybe_run()
        ventures_tick.maybe_run()
    assert state.ventures["tick"] == 1 and state.ventures["day"] == "2026-11-02"


def test_the_console_can_force_a_tick(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    background.console_command("ventures tick")
    adi.expect_text("📊 Day 1")


def test_the_board_lists_live_companies(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi")
    found(adi)
    cat.line("/ventures")
    assert "Spudly" in cat.expect_text("🦄")["text"]


# ---------------------------------------------------------------- saving

def test_companies_survive_a_restart(user):
    adi, ben = team(user)
    adi.line("/company build")
    adi.expect_text("quality")
    assert storage.save_data()
    before = company()
    saved = json.load(open(config.DATA_FILE, encoding="utf-8"))
    assert saved["ventures"]["companies"][before["id"]]["cap"] == {"p:adi": 9000, "p:ben": 1000}
    with state.lock:
        state.ventures = {}
        assert storage.load_data()
    assert company() == before


def test_a_damaged_save_doesnt_stop_the_server(user):
    with state.lock:
        storage.save_data()
        data = json.load(open(config.DATA_FILE, encoding="utf-8"))
        data["ventures"] = {"companies": {"c1": {"name": 5}, "c2": "junk"}, "tick": "x", "graveyard": "y"}
        json.dump(data, open(config.DATA_FILE, "w", encoding="utf-8"))
        assert storage.load_data()
        assert state.ventures["companies"] == {} and state.ventures["tick"] == 0


def test_an_old_client_just_sees_text(user):
    adi = user("Adi")   # no "ventures" feature: like an old client.py
    grown_up("adi")
    found(adi)
    tick()
    adi.expect_text("📊 Day 1")
    assert not any(m.get("type") == "company_event" for m in adi.messages)
