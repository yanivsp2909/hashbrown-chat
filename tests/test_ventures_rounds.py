"""💰 Funding rounds, the pure math: the investor's score and fair offer, clamping whatever the AI says, accepting a
term sheet (dilution, the option pool, the next stage), counter-offers, bridge rounds and angel terms."""
import pytest

from chatserver import cap_table, config, ventures_rounds, ventures_store


def company(**changes):
    co = ventures_store.new_company("c1", "Spudly", "spudly", "saas", "adi", tick=0)
    return {**co, **changes}


def seed_ready(**changes):
    """A Pre-seed company that meets the Seed milestones."""
    return company(**{"stage": "preseed", "stage_ticks": 4, "quality": 40.0, "customers": 1_200.0, **changes})


def test_the_score_grows_with_the_numbers_and_the_pitch():
    weak = ventures_rounds.score(seed_ready(), rating=0)
    strong = ventures_rounds.score(seed_ready(customers=3_000.0, quality=70.0, hype=60.0), rating=10)
    assert 0 <= weak < strong <= 1
    assert ventures_rounds.score(seed_ready(), 10) - ventures_rounds.score(seed_ready(), 0) == pytest.approx(0.10)


def test_the_fair_offer_is_inside_the_stage_rules():
    co = seed_ready()
    offer = ventures_rounds.fair_offer(co, "maya", rating=5)
    rules = config.ROUNDS["preseed"]
    assert rules["raise"] * 0.5 <= offer["amount"] <= rules["raise"] * 1.5
    assert offer["post"] >= rules["floor"] * 0.85 * 0.9
    low, high = rules["equity"]
    assert low * 100 <= offer["bp"] <= high * 100
    assert offer["bp"] == round(offer["amount"] / offer["post"] * cap_table.TOTAL)


def test_a_cfo_gets_a_better_valuation():
    plain = ventures_rounds.fair_offer(seed_ready(), "maya", 5)
    cfo = ventures_rounds.fair_offer(seed_ready(roles={"adi": "ceo", "ben": "cfo"}), "maya", 5)
    assert cfo["fair"] == pytest.approx(plain["fair"] * (1 + config.CFO_VALUATION_BONUS))


@pytest.mark.parametrize("amount, valuation", [(10**15, 10**18), (-5, -5), ("lots", None), (1, 1), (3.7, True)])
def test_crazy_ai_numbers_are_clamped(amount, valuation):
    co = seed_ready()
    fair = ventures_rounds.fair_offer(co, "maya", 5)
    final = ventures_rounds.clamp(co, fair, amount, valuation)
    rules = config.ROUNDS["preseed"]
    assert rules["raise"] * 0.5 <= final["amount"] <= rules["raise"] * 1.5
    assert final["post"] > final["amount"]
    assert rules["equity"][0] * 100 <= final["bp"] <= rules["equity"][1] * 100
    assert isinstance(final["amount"], int) and isinstance(final["post"], int)


def sheet_for(co, **changes):
    offer = ventures_rounds.fair_offer(co, "maya", 5)
    return {**ventures_rounds.new_sheet(co, "maya", offer, "formula", "Let's do it."), **changes}


def test_accepting_dilutes_everyone_and_moves_to_the_next_stage():
    co = seed_ready(cap={"p:adi": 6000, "p:ben": 4000})
    sheet = sheet_for(co)
    after = ventures_rounds.accept(co, sheet)
    assert after["stage"] == "seed" and after["stage_ticks"] == 0 and after["pitches"] == 0
    assert after["cash"] == co["cash"] + sheet["amount"] and after["raised"] == sheet["amount"]
    assert after["cap"]["i:maya"] == sheet["bp"]
    assert after["cap"][cap_table.POOL] > 0   # the Seed round makes the option pool
    assert sum(after["cap"].values()) == cap_table.TOTAL
    assert after["cap"]["p:adi"] / after["cap"]["p:ben"] == pytest.approx(1.5, rel=0.01)
    assert after["last_post"] == sheet["post"] and after["rounds"][-1]["investor"] == "maya"


def test_a_pre_seed_round_has_no_pool():
    co = company(stage_ticks=config.ROUND_MIN_TICKS, quality=20.0)
    after = ventures_rounds.accept(co, sheet_for(co))
    assert after["stage"] == "preseed" and cap_table.POOL not in after["cap"]


def test_counters():
    co = seed_ready()
    sheet = sheet_for(co)
    ceiling = sheet["fair"] * (1 + ventures_rounds.INVESTORS["maya"]["flex"])
    assert ventures_rounds.counter_result(sheet, int(ceiling * 0.99))[0] == "accepted"
    why, post = ventures_rounds.counter_result(sheet, int(ceiling * 1.1))
    assert why == "halfway" and sheet["post"] < post <= ceiling
    assert ventures_rounds.counter_result(sheet, int(ceiling * 2))[0] == "walked"


def test_a_counter_keeps_the_amount_and_lowers_the_equity():
    co = seed_ready()
    sheet = sheet_for(co)
    better = ventures_rounds.with_post(co, sheet, int(sheet["post"] * 1.1))
    assert better["amount"] == sheet["amount"] and better["bp"] < sheet["bp"]


def test_bridge_terms():
    amount, post, bp = ventures_rounds.bridge_terms(company())
    assert amount == int(config.ROUNDS["idea"]["raise"] * config.BRIDGE_RAISE)
    assert post == int(config.ROUNDS["idea"]["floor"] * config.BRIDGE_VALUATION)
    assert bp == round(amount / post * cap_table.TOTAL)


def test_angel_terms_price_at_the_valuation():
    dollars, bp = ventures_rounds.angel_terms(company(), 500)
    pre = config.ROUNDS["idea"]["floor"] * 0.5
    assert dollars == 500 * config.ANGEL_DOLLARS_PER_TOKEN
    assert bp == round(dollars / (pre + dollars) * cap_table.TOTAL)


@pytest.mark.parametrize("text, dollars", [("90M", 90_000_000), ("1.5b", 1_500_000_000), ("$250K", 250_000),
                                           ("12000000", 12_000_000), ("lots", None), ("-5M", None)])
def test_reading_money(text, dollars):
    assert ventures_rounds.parse_money(text) == dollars


def test_investors_fit_the_stage():
    ids = ventures_rounds.eligible(company())
    assert "dana" in ids and "maya" not in ids
    assert "kenji" not in ventures_rounds.eligible(seed_ready())


def test_investor_interest_tells_players_when_just_meeting_the_milestones_isnt_enough():
    barely = company(stage_ticks=config.ROUND_MIN_TICKS, quality=16.0)
    strong = company(stage_ticks=config.ROUND_MIN_TICKS, quality=60.0, hype=70.0, reputation=80.0)
    assert ventures_rounds.interest(barely).startswith("🥶")
    assert ventures_rounds.interest(strong).startswith("🔥")


def test_giant_money_is_not_money():
    assert ventures_rounds.parse_money("9" * 400 + "b") is None
    assert ventures_rounds.parse_money("2000000b") is None


def test_moving_equity_to_yourself_changes_nothing():
    assert cap_table.move({"p:adi": 9000, "p:ben": 1000}, "p:ben", "p:ben", 500) == {"p:adi": 9000, "p:ben": 1000}
