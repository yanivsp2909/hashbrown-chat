"""🏁 The endgame: exits under the owner's V2 rule (tax, cap, the fund first, the season's mint cap, the queue), the IPO
onto the stock market, acquisitions, partnerships, poaching, the boards and the end of a season."""
import pytest

from chatserver import config, state, ventures_deals, ventures_exits, ventures_season, ventures_store
from test_ventures_company import found, grown_up, team, tick

pytestmark = pytest.mark.integration


def company(name="Spudly"):
    with state.lock:
        return ventures_store.find(name)


def update(name, **changes):
    with state.lock:
        return ventures_store.put({**ventures_store.find(name), **changes})


def ipo_ready(name="Spudly"):
    """A Series C company that meets every IPO milestone."""
    return update(name, stage="c", stage_ticks=config.ROUND_MIN_TICKS, quality=90.0, reputation=80.0, hype=60.0,
                  customers=400_000.0, cash=50_000_000)


# ---------------------------------------------------------------- exits

def test_exit_tokens_are_taxed_and_capped():
    assert ventures_exits.tokens_for(2500, 1_000_000_000) == (5000, 1000, 4000)   # 25% of $1B, capped at 5,000
    assert ventures_exits.tokens_for(100, 10_000_000) == (2, 0, 2)   # 1% of $10M


def test_the_fund_pays_first_then_new_tokens_up_to_the_cap_then_the_queue(user, monkeypatch):
    user("Adi")
    grown_up("adi", tokens=0)
    monkeypatch.setattr(config, "VENTURES_MINT_SEASON_CAP", 300)
    with state.lock:
        ventures_store.ensure()
        state.public_fund = 200
        assert ventures_exits.pay("adi", 1000, "test") == (200, 300, 500)
        assert state.accounts["adi"]["tokens"] == 500 and state.ventures["minted"] == 300
        state.public_fund = 450
        ventures_exits.pay_queue()
        assert state.accounts["adi"]["tokens"] == 950 and state.ventures["exit_queue"][0]["tokens"] == 50


# ---------------------------------------------------------------- the IPO and the stock

def test_an_ipo_lists_the_company_and_pays_its_founders(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    found(adi)
    ipo_ready()
    before = state.accounts["adi"]["tokens"]
    adi.line("/company ipo")
    adi.expect_text("is PUBLIC")
    co = company()
    assert co["stage"] == "public" and co["cap"]["public"] == config.IPO_NEW_SHARES_PERCENT * 100
    assert "#spudly" in state.stocks and state.stocks["#spudly"]["price"] >= 1
    assert state.accounts["adi"]["tokens"] == before + config.EXIT_MAX_TOKENS * (100 - config.EXIT_TAX_PERCENT) // 100
    assert ventures_store.ensure()["exits"][-1]["kind"] == "IPO"
    cat.line("/buy #spudly 1")
    cat.expect_text("📈 You bought 1 #SPUDLY")
    assert state.accounts["cat"]["portfolio"]["#spudly"] == 1


def test_the_stock_follows_the_valuation_and_a_death_delists_it(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    found(adi)
    ipo_ready()
    adi.line("/company ipo")
    adi.expect_text("is PUBLIC")
    cat.line("/buy #spudly 2")
    cat.expect_text("📈 You bought 2 #SPUDLY")
    update("Spudly", valuation=company()["valuation"] * 3)
    price = state.stocks["#spudly"]["price"]
    with state.lock:
        ventures_deals.stock_tick()
    assert state.stocks["#spudly"]["price"] > price
    with state.lock:
        state.public_fund = 100_000
        before = state.accounts["cat"]["tokens"]
        ventures_deals.delist(company(), "the company died")
    assert "#spudly" not in state.stocks and "#spudly" not in state.accounts["cat"]["portfolio"]
    assert state.accounts["cat"]["tokens"] > before


def test_no_ipo_without_the_milestones(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    adi.line("/company ipo")
    adi.expect_text("milestones", kind="error")


# ---------------------------------------------------------------- deals

def two_companies(user):
    adi, ben = user("Adi"), user("Ben")
    grown_up("adi", "ben")
    found(adi, "Bigco", "saas")
    found(ben, "Smallco", "ai")
    update("Bigco", stage="a", cash=20_000_000)
    update("Smallco", valuation=2_000_000)
    return adi, ben


def test_an_acquisition_pays_the_sellers_and_ends_the_company(user):
    adi, ben = two_companies(user)
    adi.line("/company acquire Smallco 1M")
    adi.expect_text("At least", kind="error")
    adi.line("/company acquire Smallco 3M")
    card = ben.expect(lambda m: isinstance(m.get("acquisition"), dict))
    assert card["acquisition"]["amount"] == 3_000_000
    before = state.accounts["ben"]["tokens"]
    ben.line("/company sell accept")
    ben.expect_text("Exit!")
    assert company("Smallco")["status"] == "acquired" and company("Bigco")["cash"] == 17_000_000
    assert state.accounts["ben"]["tokens"] > before
    assert company("Bigco")["synergy"] == config.PARTNER_BONUS   # another sector: a lasting boost


def test_no_self_dealing(user):
    adi, ben = team(user)   # Ben is in Spudly
    grown_up("adi", "ben")
    cat = user("Cat")
    grown_up("cat")
    found(cat, "Catco", "ai")
    with state.lock:
        group = state.groups["catco"]
        state.groups["catco"] = {**group, "members": group["members"] + ["ben"]}   # Ben is on both sides
    update("Spudly", stage="a", cash=20_000_000)
    adi.line("/company acquire Catco 5M")
    adi.expect_text("both sides", kind="error")


def test_partners_from_different_sectors(user):
    adi, ben = two_companies(user)
    adi.line("/company partner Smallco")
    ben.expect(lambda m: isinstance(m.get("partner_offer"), dict))
    ben.line("/company partner accept Bigco")
    ben.expect_text("Partners with Bigco")
    assert company("Bigco")["partner"]["with"] == company("Smallco")["id"]


def test_poaching(user, monkeypatch):
    adi, ben = two_companies(user)
    update("Smallco", staff={"engineer": 1, "sales": 0, "marketer": 0})
    monkeypatch.setattr(ventures_deals.random, "random", lambda: 0.0)
    adi.line("/company poach Smallco engineer")
    adi.expect_text("Poached 1 engineer")
    assert company("Bigco")["staff"]["engineer"] == 1 and company("Smallco")["staff"]["engineer"] == 0
    adi.line("/company poach Smallco sales")
    adi.expect_text("Nobody to poach", kind="error")


# ---------------------------------------------------------------- the boards and the season

def test_the_best_investors_board(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    found(adi)
    cat.line("/invest Spudly 100")
    cat.expect_text("waiting")
    adi.line("/company angel accept Cat")
    cat.expect_text("accepted")
    update("Spudly", valuation=500_000_000)
    with state.lock:
        board = ventures_season.investors_board()
    assert board[0]["name"] == "Cat" and board[0]["tokens_in"] == 100 and board[0]["multiple"] > 1


def test_a_season_ends_with_payouts_a_hall_of_fame_and_a_fresh_start(user):
    adi = user("Adi", features=["ventures"])
    grown_up("adi")
    found(adi)
    update("Spudly", valuation=100_000_000, last_post=100_000_000, acted=True, cash=10_000_000)
    with state.lock:
        ventures_store.set_field("tick", config.SEASON_TICKS - 1)
    before = state.accounts["adi"]["tokens"]
    tick()
    adi.expect_text("season 2")
    assert ventures_store.ensure()["season"] == 2 and ventures_store.ensure()["tick"] == 0
    assert company()["status"] == "ended"
    assert state.accounts["adi"]["tokens"] > before   # 20% of an exit
    fame = ventures_store.ensure()["fame"]
    assert fame[0]["award"] == "Most valuable company" and fame[0]["name"] == "Spudly"
    assert "ventures_champion" in state.accounts["adi"]["achievements"]
    adi.line("/company found Again saas")
    adi.expect_text("Founded Again")


def test_the_home_shows_the_boards(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    adi.send({"type": "get_ventures"})
    home = adi.expect(lambda m: m.get("type") == "ventures")
    assert "investors" in home and "fame" in home and home["season"]["mint_cap"] == config.VENTURES_MINT_SEASON_CAP


# ---------------------------------------------------------------- after the reviews

def test_an_offer_cant_be_accepted_after_the_ipo(user):
    adi, ben = two_companies(user)
    update("Smallco", stage="c", stage_ticks=config.ROUND_MIN_TICKS, quality=90.0, reputation=80.0, hype=60.0,
           customers=40_000.0, cash=50_000_000, valuation=2_000_000)
    adi.line("/company acquire Smallco 3M")
    ben.expect(lambda m: isinstance(m.get("acquisition"), dict))
    ben.line("/company ipo")
    ben.expect_text("is PUBLIC")
    assert ventures_store.ensure()["acquisitions"] == {}   # the IPO dropped the offer
    ben.line("/company sell accept")
    ben.expect_text("No offer", kind="error")
    assert company("Smallco")["status"] == "alive"


def test_an_offer_far_above_the_value_is_refused_and_exits_count_near_the_value(user):
    adi, ben = two_companies(user)
    adi.line("/company acquire Smallco 9M")
    adi.expect_text("At most 2x", kind="error")
    adi.line("/company acquire Smallco 4M")
    ben.expect(lambda m: isinstance(m.get("acquisition"), dict))
    ben.line("/company sell accept")
    ben.expect_text("Exit!")
    assert ventures_store.ensure()["exits"][-1]["value"] == 3_000_000   # 1.5x the $2M valuation, not the $4M paid


def test_a_second_buyer_cant_replace_a_waiting_offer(user):
    adi, ben = two_companies(user)
    cat = user("Cat")
    grown_up("cat")
    found(cat, "Thirdco", "game")
    update("Thirdco", stage="a", cash=20_000_000)
    adi.line("/company acquire Smallco 3M")
    ben.expect(lambda m: isinstance(m.get("acquisition"), dict))
    cat.line("/company acquire Smallco 3M")
    cat.expect_text("already has an offer", kind="error")


def test_the_deal_options_only_for_the_ceo_of_another_company(user):
    adi, ben = two_companies(user)
    cat = user("Cat")
    for client, expect_deals in ((adi, True), (cat, False)):
        client.send({"type": "get_company", "company": company("Smallco")["id"]})
        packet = client.expect(lambda m: m.get("type") == "company")["company"]
        assert (packet["deals"] is not None) == expect_deals and "numbers" not in packet
    adi.send({"type": "get_company", "company": company("Smallco")["id"]})
    deals = adi.expect(lambda m: m.get("type") == "company")["company"]["deals"]
    assert deals["acquire_min"] == 1_200_000 and deals["acquire_max"] == 4_000_000 and deals["poach_ap"] == config.POACH_AP


def test_a_delisted_company_says_so(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    ipo_ready()
    adi.line("/company ipo")
    adi.expect_text("is PUBLIC")
    with state.lock:
        ventures_deals.delist(company(), "the season ended")
    adi.send({"type": "get_company", "company": company()["id"]})
    ipo = adi.expect(lambda m: m.get("type") == "company")["company"]["ipo"]
    assert ipo["listed"] is False


def test_delisting_hands_back_the_cost_and_pays_profit_only_from_the_fund(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    found(adi)
    ipo_ready()
    adi.line("/company ipo")
    adi.expect_text("is PUBLIC")
    cat.line("/buy #spudly 2")
    cat.expect_text("📈 You bought 2 #SPUDLY")
    spent = state.accounts["cat"]["spent"]["#spudly"]
    state.stocks["#spudly"]["price"] *= 5   # a big rise
    with state.lock:
        state.public_fund = 0
        before = state.accounts["cat"]["tokens"]
        ventures_deals.delist(company(), "test")
    assert state.accounts["cat"]["tokens"] == before + spent   # the cost back; no fund, no profit
