"""🏢 The website's Ventures screens: {"type": "get_ventures"} / {"type": "get_company"} -> the "ventures" and
"company" packets, refreshed when something changes. They only show things; buttons send the usual commands."""
import pytest

from chatserver import config, state, ventures_view
from test_ventures_company import found, grown_up, team

pytestmark = pytest.mark.integration


def home_of(client):
    client.send({"type": "get_ventures"})
    return client.expect(lambda m: m.get("type") == "ventures")


def hq_of(client, cid):
    client.send({"type": "get_company", "company": cid})
    return client.expect(lambda m: m.get("type") == "company")["company"]


def push():
    with state.lock:
        ventures_view.push_updates()


def test_the_home_without_a_company(user):
    adi = user("Adi")
    home = home_of(adi)
    assert home["mine"] is None and not home["me"]["can_found"] and "24 hours" in home["me"]["why"]
    assert [s["key"] for s in home["sectors"]] == list(config.SECTORS)
    assert all(s["pitch"] and s["twist"] and 1 <= s["difficulty"] <= 3 for s in home["sectors"])
    assert home["season"]["days"] == config.SEASON_TICKS and home["season"]["next_tick"] > 0


def test_the_home_with_a_company_and_the_board(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi")
    co = found(adi)
    assert home_of(adi)["mine"]["id"] == co["id"]
    board = home_of(cat)["board"]
    assert board[0]["name"] == "Spudly" and board[0]["team"] == ["Adi"]


def test_a_member_sees_everything_an_outsider_only_the_public_part(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi")
    co = found(adi)
    mine = hq_of(adi, co["id"])
    assert mine["member"] and mine["numbers"]["cash"] == config.START_CASH and mine["ap"] == config.AP_BASE
    assert {a["name"] for a in mine["actions"]} >= {"build", "hire", "marketing"}
    assert mine["you"]["ceo"] and mine["timeline"][0]["state"] == "now"
    assert mine["sector_panel"]["sector"] == "saas" and mine["sector_panel"]["price"] == 1.0
    assert {"priceup", "retention"} <= {a["name"] for a in mine["actions"] if a["sector"]}
    theirs = hq_of(cat, co["id"])
    assert not theirs["member"] and "numbers" not in theirs and "actions" not in theirs and "pitch" not in theirs
    assert "sector_panel" not in theirs and "fumes" not in theirs and "fumes" not in home_of(cat)["board"][0]
    assert theirs["cap"] == [{"name": "Adi", "kind": "player", "bp": 10000}]


def test_the_hq_refreshes_after_a_command(user):
    adi = user("Adi")
    grown_up("adi")
    co = found(adi)
    hq_of(adi, co["id"])
    adi.line("/company build")
    adi.expect_text("quality")
    push()
    fresh = adi.expect(lambda m: m.get("type") == "company")["company"]
    assert fresh["ap"] == config.AP_BASE - 1


def test_an_invite_shows_on_the_invitees_home(user):
    adi, ben = user("Adi"), user("Ben")
    grown_up("adi", "ben")
    found(adi)
    adi.line("/company invite Ben cto 10")
    ben.expect(lambda m: isinstance(m.get("company_invite"), dict))
    invite = home_of(ben)["invites"][0]
    assert invite["name"] == "Spudly" and invite["role"] == "cto" and invite["bp"] == 1000 and invite["from"] == "Adi"


def test_investments_and_waiting_angel_offers(user):
    adi, cat = user("Adi"), user("Cat")
    grown_up("adi", "cat")
    co = found(adi)
    cat.line("/invest Spudly 100")
    cat.expect_text("waiting")
    waiting = home_of(cat)["investments"]["waiting"]
    assert waiting[0]["name"] == "Spudly" and waiting[0]["tokens"] == 100
    assert hq_of(adi, co["id"])["angels"][0]["name"] == "Cat"
    adi.line("/company angel accept Cat")
    cat.expect_text("accepted")
    held = home_of(cat)["investments"]["held"]
    assert held[0]["name"] == "Spudly" and held[0]["bp"] > 0 and held[0]["tokens"] == 100


def test_the_team_and_pitch_in_the_hq(user):
    adi, ben = team(user)
    hq = hq_of(ben, state.groups["spudly"]["company"])
    assert [(t["name"], t["role"]) for t in hq["team"]] == [("Adi", "ceo"), ("Ben", "cto")]
    assert not hq["pitch"]["can_pitch"] and "needs" in hq["pitch"]["why"]
    assert hq["interest"]["level"] == "low"


def test_closing_stops_the_updates_and_a_bad_id_is_refused(user):
    adi = user("Adi")
    grown_up("adi")
    found(adi)
    adi.send({"type": "get_company", "company": "c999"})
    adi.expect_text("No company", kind="error")
    home_of(adi)
    adi.send({"type": "ventures_closed"})
    adi.sync()
    adi.line("/company build")
    adi.expect_text("quality")
    push()
    adi.sync()
    assert not any(m.get("type") == "company" for m in adi.messages[-6:])
