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
    adi.expect_text("action point", kind="error")


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
    adi.line("/company invite Ben engineer")
    ben.expect(lambda m: isinstance(m.get("company_invite"), dict))
    found(ben, "Fryware", "ai")   # (founded after the invite came)
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
    user("Cat")
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


def test_a_save_with_infinite_numbers_or_a_broken_cap_table_still_loads(user):
    adi = user("Adi")
    grown_up("adi")
    co = found(adi)
    with state.lock:
        storage.save_data()
    text = open(config.DATA_FILE, encoding="utf-8").read()
    data = json.loads(text)
    data["ventures"]["companies"][co["id"]]["cash"] = float("inf")
    data["ventures"]["companies"][co["id"]]["cap"] = {}
    data["ventures"]["next_id"] = "broken"
    with open(config.DATA_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps(data))   # (json writes Infinity, which json.load reads back)
    with state.lock:
        assert storage.load_data()
    loaded = company()
    assert loaded["cash"] == config.START_CASH and loaded["cap"] == {"p:adi": 10000}
    assert state.ventures["next_id"] > int(co["id"][1:])


# ---------------------------------------------------------------- after the code review

def test_only_the_ceo_can_shut_down(user):
    adi, ben = team(user)
    ben.line("/company shutdown Spudly")
    ben.expect_text("Only the CEO", kind="error")
    assert company()["status"] == "alive"


def test_an_expired_invite_is_no_way_in(user):
    adi, ben = user("Adi"), user("Ben")
    grown_up("adi", "ben")
    found(adi)
    adi.line("/company invite Ben engineer")
    ben.expect(lambda m: isinstance(m.get("company_invite"), dict))
    with state.lock:
        group = state.groups["spudly"]
        group["invites"]["ben"]["at"] -= 48 * 3600
    ben.line("/join Spudly")
    ben.expect_text("ask its CEO", kind="error")
    assert "ben" not in state.groups["spudly"]["requests"]
    adi.line("/approve Ben")
    adi.expect_text("🏢", kind="error")


def test_rejoining_doesnt_put_vested_shares_back_on_the_clock(user):
    adi, ben = team(user)
    with state.lock:
        co = company()
        ventures_store.put({**co, "age": 40})   # long enough: all of Ben's 10% vested
    ben.line("/company leave")
    ben.expect_text("You left")
    assert company()["cap"]["p:ben"] == 1000
    adi.line("/company invite Ben engineer 1")
    ben.expect(lambda m: isinstance(m.get("company_invite"), dict))
    ben.line("/join Spudly")
    ben.expect_text("joined Spudly")
    assert company()["grants"]["ben"] == {"bp": 100, "tick": 40}


def test_a_second_grant_vests_from_its_own_day(user):
    adi, ben = team(user)
    with state.lock:
        ventures_store.put({**company(), "age": 28})
    adi.line("/company grant Ben 10")
    adi.expect_text("gave Ben 10%")
    grant = company()["grants"]["ben"]
    assert grant["bp"] == 2000 and grant["tick"] == 14   # halfway between day 0 (1000) and day 28 (1000)


def test_leaving_after_a_round_keeps_a_quarter_of_the_diluted_grant(user):
    from chatserver import ventures_rounds
    adi, ben = team(user)
    with state.lock:
        co = {**company(), "stage_ticks": 4, "quality": 40.0}
        offer = ventures_rounds.fair_offer(co, "dana", 5)
        ventures_store.put(ventures_rounds.accept(co, ventures_rounds.new_sheet(co, "dana", offer, "formula", "")))
    diluted = company()["cap"]["p:ben"]
    ben.line("/company leave")
    ben.expect_text("You left")
    assert company()["cap"]["p:ben"] == pytest.approx(diluted * 0.25, abs=2)


def test_an_old_offer_isnt_reused_by_a_plain_invite(user):
    adi, ben = user("Adi"), user("Ben")
    grown_up("adi", "ben")
    found(adi)
    adi.line("/company invite Ben cto 20")
    ben.expect(lambda m: isinstance(m.get("company_invite"), dict))
    ben.line("/invites decline Spudly")
    ben.expect_text("said no")
    time.sleep(6)   # (an offer counts only with the invite it came with)
    adi.line("/invite Ben")
    adi.expect_text("Invited Ben")
    ben.line("/join Spudly")
    ben.expect_text("joined Spudly")
    assert company()["roles"]["ben"] == "engineer" and "p:ben" not in company()["cap"]


def test_one_broken_company_doesnt_stop_the_tick(user):
    adi, ben = user("Adi"), user("Ben")
    grown_up("adi", "ben")
    found(adi, "Aaa")
    found(ben, "Bbb")
    with state.lock:
        broken = ventures_store.find("Aaa")
        ventures_store.put({**broken, "staff": {}})   # a record the tick can't read
    tick()
    assert company("Bbb")["age"] == 1


def test_the_team_size_limit_at_join(user, monkeypatch):
    monkeypatch.setattr(config, "TEAM_MAX_PLAYERS", 1)
    adi, _ = user("Adi"), user("Ben")
    grown_up("adi", "ben")
    found(adi)
    adi.line("/company invite Ben engineer")
    adi.expect_text("at most 1 players", kind="error")


# ---------------------------------------------------------------- after the bug hunt

def test_on_fumes_free_actions_and_layoffs_still_work(user):
    adi = user("Adi")
    grown_up("adi")
    co = found(adi)
    with state.lock:
        ventures_store.put({**co, "cash": -16_500, "fumes": True, "staff": {"engineer": 2, "sales": 0, "marketer": 0}})
    adi.line("/company build")
    adi.expect_text("quality")
    adi.line("/company layoff engineer 1")
    adi.expect_text("Let 1 engineer")
    adi.line("/company layoff engineer -1")
    adi.expect_text("lay off 1 to 1", kind="error")
    adi.line("/company layoff engineer ²")
    adi.expect_text("lay off 1 to 1", kind="error")


def test_promised_equity_comes_from_whoever_promised_it(user):
    adi, ben = team(user)
    cat = user("Cat")
    grown_up("cat")
    adi.line("/company invite Cat cmo 20")
    cat.expect(lambda m: isinstance(m.get("company_invite"), dict))
    adi.line("/company ceo Ben")
    adi.expect_text("CEO of Spudly")
    cat.line("/join Spudly")
    cat.expect_text("joined Spudly")
    cap = company()["cap"]
    assert cap["p:cat"] == 2000 and cap["p:ben"] == 1000 and cap["p:adi"] == 7000


def test_a_counter_must_ask_for_more(user):
    from test_ventures_pitch import is_sheet, make_ready, pitch_through
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    make_ready()
    pitch_through(adi)
    sheet = adi.expect(is_sheet, timeout=10)["term_sheet"]
    adi.line(f"/offer counter {sheet['post'] // 2}")
    adi.expect_text("HIGHER", kind="error")
    assert not company()["sheet"]["countered"]


def test_shutting_down_closes_the_open_term_sheet(user):
    from test_ventures_pitch import is_sheet, make_ready, pitch_through
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    make_ready()
    pitch_through(adi)
    sheet = adi.expect(is_sheet, timeout=10)["term_sheet"]
    adi.line("/company shutdown Spudly")
    adi.expect(lambda m: m.get("type") == "term_sheet_closed" and m.get("id") == sheet["id"] and m.get("why") == "gone")


def test_no_invite_card_for_someone_already_in_a_company(user):
    adi, ben = user("Adi"), user("Ben")
    grown_up("adi", "ben")
    found(adi)
    found(ben, "Fryware", "ai")
    adi.line("/company invite Ben engineer")
    adi.expect_text("already in Fryware", kind="error")


def test_the_ceo_hears_back_from_another_room(user):
    adi, ben = team(user)
    adi.line("/lobby")
    adi.line("/company grant Ben 5")
    adi.expect_text("gave Ben 5%")


def test_bank_in_a_company_explains_itself(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    adi.line("/bank")
    adi.expect_text("game dollars", kind="error")
