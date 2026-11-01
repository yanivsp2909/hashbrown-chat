"""
🎤 The pitch room and the money on a real server: /pitch with the AI investor (the fake AI only) and without it,
the term sheet card, /offer accept · decline · counter, the bridge round, and angel investing with held tokens.
The AI only writes words: whatever numbers it sends, the server clamps them.
"""
import json
import time

import pytest

from chatserver import cap_table, config, state, ventures_angels, ventures_rounds, ventures_store
from test_ventures_company import found, grown_up, team

pytestmark = pytest.mark.integration


def company(name="Spudly"):
    with state.lock:
        return ventures_store.find(name)


def make_ready(name="Spudly", **changes):
    """Give the company the next round's milestones."""
    with state.lock:
        co = ventures_store.find(name)
        ventures_store.put({**co, "stage_ticks": config.ROUND_MIN_TICKS, "quality": 40.0, **changes})


def is_sheet(m):
    return m.get("type") == "msg" and isinstance(m.get("term_sheet"), dict)


def is_question(m):
    """The investor's question (not its greeting, which asks for the pitch)."""
    return (m.get("type") == "chat" and isinstance(m.get("investor"), dict) and "?" in m.get("text", "")
            and "/pitch send" not in m.get("text", ""))


def pitch_through(client, answers=2):
    """Pitch, answer every question, and wait for the end (an offer or a pass)."""
    client.line("/pitch")
    client.expect_text("/pitch send")
    client.line("We make potato software for every kitchen. 500 users love it and pay $10 a month.")
    client.line("/pitch send")
    for _ in range(answers):
        client.expect(is_question, timeout=10)
        client.line("Our churn is low and we grow 20% a week.")
        client.line("/pitch send")


# ---------------------------------------------------------------- without the AI (the formula investor)

def test_a_whole_pitch_without_the_ai_ends_in_a_term_sheet(user):
    adi = user("Adi", features=["ventures"])
    grown_up("adi")
    found(adi)
    make_ready()
    pitch_through(adi)
    card = adi.expect(is_sheet, timeout=10)
    sheet = card["term_sheet"]
    assert "/offer accept" in card["text"]
    low, high = config.ROUNDS["idea"]["equity"]
    assert low * 100 <= sheet["equity_bp"] <= high * 100
    assert company()["ap"] == config.AP_BASE - config.PITCH_AP
    adi.line("/offer accept")
    adi.expect_text("raised")
    co = company()
    assert co["stage"] == "preseed" and co["cash"] == config.START_CASH + sheet["amount"]
    assert co["cap"]["p:adi"] == cap_table.TOTAL - sheet["equity_bp"]
    assert {"type": "term_sheet_closed", "id": sheet["id"], "why": "accepted"} in [
        {k: m.get(k) for k in ("type", "id", "why")} for m in adi.messages]


def test_no_pitch_before_the_milestones(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    adi.line("/pitch")
    adi.expect_text("needs", kind="error")
    assert company()["ap"] == config.AP_BASE and company()["pitches"] == 0


def test_only_the_c_level_pitches_and_only_one_at_a_time(user):
    adi, ben = team(user)
    with state.lock:
        ventures_store.update(company()["id"], roles={"adi": "ceo", "ben": "engineer"})
    make_ready()
    ben.line("/pitch")
    ben.expect_text("C-level", kind="error")
    adi.line("/pitch")
    adi.expect_text("/pitch send")
    adi.line("/pitch")
    adi.expect_text("already", kind="error")


def test_three_pitches_per_stage(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    for _ in range(config.PITCHES_PER_STAGE):
        make_ready(ap=config.AP_MAX, pitch=None)
        adi.line("/pitch")
        adi.expect_text("/pitch send")
        adi.line("/pitch stop")
        adi.expect_text("walked out")
    make_ready(ap=config.AP_MAX)
    adi.line("/pitch")
    adi.expect_text("pitches", kind="error")


def test_only_lines_in_the_company_chat_count(user):
    adi, ben = team(user)
    make_ready()
    adi.line("/pitch")
    adi.expect_text("/pitch send")
    adi.line("/lobby")
    adi.line("this is the lobby, not the pitch")
    adi.line("/pitch send")
    adi.expect_text("Say your pitch", kind="error")
    ben.line("Ben here: we are great")
    ben.line("/pitch send")
    ben.expect(is_question, timeout=10)


def test_decline_and_expiry(user):
    adi = user("Adi", features=["ventures"])
    grown_up("adi")
    found(adi)
    make_ready()
    pitch_through(adi)
    adi.expect(is_sheet, timeout=10)
    adi.line("/offer decline")
    adi.expect(lambda m: m.get("type") == "term_sheet_closed" and m.get("why") == "declined")
    assert company()["sheet"] is None and company()["stage"] == "idea"
    make_ready(ap=config.AP_MAX)
    pitch_through(adi)
    adi.expect(is_sheet, timeout=10)
    with state.lock:
        co = company()
        ventures_store.put({**co, "sheet": {**co["sheet"], "expires": time.time() - 1}})
        ventures_rounds.expire_due()
    adi.expect(lambda m: m.get("type") == "term_sheet_closed" and m.get("why") == "expired")


def test_only_the_ceo_answers_a_term_sheet(user):
    adi, ben = team(user)
    make_ready()
    pitch_through(adi)
    adi.expect(is_sheet, timeout=10)
    ben.line("/offer accept")
    ben.expect_text("Only the CEO", kind="error")


def test_a_counter_once(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    make_ready()
    pitch_through(adi)
    sheet = adi.expect(is_sheet, timeout=10)["term_sheet"]
    adi.line(f"/offer counter {sheet['post'] * 100}")
    adi.expect_text("walked away", timeout=10)
    assert company()["sheet"] is None


def test_a_bridge_round_when_on_fumes(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    adi.line("/company bridge")
    adi.expect_text("on fumes", kind="error")
    with state.lock:
        ventures_store.update(company()["id"], fumes=True, cash=-10)
    adi.line("/company bridge")
    adi.expect_text("Bridge Capital")
    co = company()
    assert co["cash"] > 0 and "i:bridge" in co["cap"] and co["stage"] == "idea"
    adi.line("/company bridge")
    adi.expect_text("once", kind="error")


# ---------------------------------------------------------------- with the (fake) AI

def turn(question, rating=6):
    return json.dumps({"reply": "Nice.", "question": question, "pitch_rating": rating})


def decision(**fields):
    return json.dumps({"decision": "offer", "valuation": 4_000_000, "amount": 600_000, "reasons": "Good team.",
                       "message": "I'm in!", "pitch_rating": 7, **fields})


def test_the_ai_investor_asks_its_own_questions_and_its_offer_is_used(user, fake_hashbrown):
    fake_hashbrown.answers = [turn("Who pays you?"), turn("Why now?"), decision()]
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    make_ready()
    pitch_through(adi)
    sheet = adi.expect(is_sheet, timeout=10)["term_sheet"]
    assert any("Who pays you?" in t for t in adi.texts()) and any("I'm in!" in t for t in adi.texts())
    assert sheet["amount"] == 600_000
    body = fake_hashbrown.requests[0][1]
    assert body["text"]["format"]["type"] == "json_schema" and body["text"]["format"]["strict"] is True
    assert "<pitch>" in json.dumps(body["input"]) and "THE FACTS" in body["instructions"]


def test_crazy_ai_numbers_never_make_money_out_of_nothing(user, fake_hashbrown):
    fake_hashbrown.answers = [turn("Q1?"), turn("Q2?"), decision(valuation=10**15, amount=10**12, pitch_rating=99)]
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    make_ready()
    pitch_through(adi)
    sheet = adi.expect(is_sheet, timeout=10)["term_sheet"]
    rules = config.ROUNDS["idea"]
    assert sheet["amount"] <= rules["raise"] * 1.5 and sheet["equity_bp"] >= rules["equity"][0] * 100


def test_broken_ai_answers_fall_back_to_the_formula(user, fake_hashbrown):
    fake_hashbrown.answers = ["not json at all", json.dumps({"question": 5}), "{\"decision\": \"maybe\"}"]
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    make_ready()
    pitch_through(adi)
    adi.expect(lambda m: is_sheet(m) or "passes" in m.get("text", ""), timeout=10)


def test_an_ai_pass_is_a_pass(user, fake_hashbrown):
    fake_hashbrown.answers = [turn("Q1?"), turn("Q2?"), decision(decision="pass", message="Not for me.")]
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    make_ready()
    pitch_through(adi)
    adi.expect_text("Not for me.", timeout=10)
    assert company()["sheet"] is None


def test_a_deployment_without_json_format_still_works(user, fake_hashbrown):
    fake_hashbrown.reject_text_format = True
    fake_hashbrown.answers = [turn("Who pays you?")]
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    make_ready()
    adi.line("/pitch")
    adi.expect_text("/pitch send")
    adi.line("/pitch We make potato software.")
    adi.expect_text("Who pays you?", timeout=10)
    assert "text" in fake_hashbrown.requests[0][1] and "text" not in fake_hashbrown.requests[1][1]
    assert state.hashbrown_no_json_format


def test_the_investor_answers_in_hebrew_to_a_hebrew_pitch(user, fake_hashbrown):
    fake_hashbrown.answers = [turn("מי משלם לכם?")]
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    make_ready()
    adi.line("/pitch")
    adi.expect_text("/pitch send")
    adi.line("/pitch אנחנו בונים תוכנה לתפוחי אדמה לכל מטבח")
    adi.expect_text("מי משלם", timeout=10)
    assert "Answer in Hebrew" in fake_hashbrown.requests[0][1]["instructions"]


# ---------------------------------------------------------------- angels

def test_an_angel_offer_holds_the_tokens_until_the_ceo_says_yes(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    found(adi)
    fund_before = state.public_fund
    cat.line("/invest Spudly 200")
    cat.expect_text("waiting")
    assert state.accounts["cat"]["tokens"] == 800
    adi.expect_text("/company angel accept Cat")
    adi.line("/company angel accept Cat")
    cat.expect_text("accepted")
    co = company()
    assert co["cash"] == config.START_CASH + 200 * config.ANGEL_DOLLARS_PER_TOKEN
    assert co["cap"]["p:cat"] == ventures_rounds.angel_terms({**co, "cap": {}}, 200)[1]
    assert state.public_fund == fund_before + 200


def test_a_declined_or_late_angel_offer_comes_back(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    found(adi)
    cat.line("/invest Spudly 100")
    cat.expect_text("waiting")
    adi.line("/company angel decline Cat")
    cat.expect_text("said no")
    assert state.accounts["cat"]["tokens"] == 1000
    cat.line("/invest Spudly 100")
    cat.expect_text("waiting")
    with state.lock:
        offers = state.ventures["angels"]
        ventures_store.set_field("angels", {k: {**v, "at": 0} for k, v in offers.items()})
        ventures_angels.expire_due()
    cat.expect_text("came back")
    assert state.accounts["cat"]["tokens"] == 1000


@pytest.mark.parametrize("line, error", [("/invest Spudly 10", "at least"), ("/invest Spudly 5000", "have"),
                                         ("/invest Nowhere 100", "No company"), ("/invest Spudly 600", "a day")])
def test_angel_limits(user, line, error):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    with state.lock:
        state.accounts["cat"]["tokens"] = 4000
    found(adi)
    cat.line(line)
    cat.expect_text(error, kind="error")


def test_a_new_account_cant_be_an_angel(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi")
    found(adi)
    cat.line("/invest Spudly 60")
    cat.expect_text("hours old", kind="error")


def test_the_age_rule_can_be_switched_off_for_a_test_server(user, monkeypatch):
    monkeypatch.setattr(config, "VENTURES_MIN_AGE_HOURS", 0)
    adi = user("Adi")
    with state.lock:
        state.accounts["adi"]["tokens"] = 1000
    found(adi)


# ---------------------------------------------------------------- after the security review

def test_the_angel_price_is_fixed_when_the_offer_is_made(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    found(adi)
    cat.line("/invest Spudly 200")
    cat.expect_text("waiting")
    promised = next(iter(state.ventures["angels"].values()))["bp"]
    with state.lock:   # the company got much more valuable before the CEO answered
        ventures_store.update(company()["id"], last_post=500_000_000)
    adi.line("/company angel accept Cat")
    cat.expect_text("accepted")
    assert company()["cap"]["p:cat"] == promised


def test_an_angel_can_take_an_offer_back(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    found(adi)
    cat.line("/invest Spudly 200")
    cat.expect_text("waiting")
    cat.line("/invest cancel Spudly")
    cat.expect_text("took back")
    assert state.accounts["cat"]["tokens"] == 1000 and state.ventures["angels"] == {}
    cat.line("/invest Spudly 500")   # the day's allowance came back too
    cat.expect_text("waiting")


def test_held_angel_tokens_still_count_in_the_token_supply(user):
    from chatserver import economy
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    found(adi)
    before = economy.total_supply()
    cat.line("/invest Spudly 200")
    cat.expect_text("waiting")
    assert economy.total_supply() == before


def test_only_the_c_level_sends_or_stops_a_pitch(user):
    adi, ben = team(user)
    with state.lock:
        ventures_store.update(company()["id"], roles={"adi": "ceo", "ben": "engineer"})
    make_ready()
    adi.line("/pitch")
    adi.expect_text("/pitch send")
    ben.line("/pitch stop")
    ben.expect_text("C-level", kind="error")
    ben.line("we are amazing")
    ben.line("/pitch send")
    ben.expect_text("C-level", kind="error")
    assert company()["pitch"] is not None


def test_an_old_term_sheet_button_doesnt_accept_the_new_one(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    make_ready()
    pitch_through(adi)
    adi.expect(is_sheet, timeout=10)
    adi.line("/offer accept c1-idea-123")
    adi.expect_text("isn't open any more", kind="error")
    assert company()["stage"] == "idea"
