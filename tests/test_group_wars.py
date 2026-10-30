"""⚔️ Group wars: an admin declares war on another group, its admin accepts; for WAR_MINUTES every match a
member wins against a member of the other group scores a point; the winner takes WAR_PRIZE from the loser's bank."""
import pytest

import games
from chatserver import config, matches, state, wars

pytestmark = pytest.mark.integration


def two_groups(user):
    """Adi owns #Red, Ben owns #Blue."""
    adi, ben = user("Adi"), user("Ben")
    for client, name in ((adi, "Red"), (ben, "Blue")):
        client.line(f"/create {name}")
        client.expect_text("Created")
    return adi, ben


def start_war(adi, ben):
    adi.line("/war Blue")
    ben.expect_text("⚔️ #Red declared war")
    ben.line("/war accept Red")
    adi.expect_text("⚔️ The war is on")
    return state.wars[0]


def win(winner, loser):
    with state.lock:
        matches.start_match(games.TicTacToe, winner, loser, 0)
        matches.finish_match(state.matches[winner], winner)


def test_declaring_and_accepting_starts_a_war(user):
    adi, ben = two_groups(user)
    war = start_war(adi, ben)
    assert {war["a"], war["b"]} == {"red", "blue"} and war["points"] == {"red": 0, "blue": 0}


def test_wins_against_the_other_group_score_points(user):
    adi, ben = two_groups(user)
    war = start_war(adi, ben)
    win("adi", "ben")
    win("adi", "ben")
    win("ben", "adi")
    assert war["points"] == {"red": 2, "blue": 1}
    adi.line("/war")
    assert "#Red 2" in adi.expect_text("⚔️ #Red vs #Blue")["text"]


def test_the_winner_takes_the_prize_from_the_losers_bank(user):
    adi, ben = two_groups(user)
    state.groups["blue"]["bank"] = config.WAR_PRIZE + 50
    war = start_war(adi, ben)
    win("adi", "ben")
    red_before = state.groups["red"]["bank"]
    with state.lock:
        wars.end_war(war)
    assert state.groups["red"]["bank"] == red_before + config.WAR_PRIZE
    assert state.groups["blue"]["bank"] == 50
    ben.expect_text("🏆 #Red won the war")
    assert state.wars == []


def test_a_tie_moves_nothing(user):
    adi, ben = two_groups(user)
    war = start_war(adi, ben)
    banks = (state.groups["red"]["bank"], state.groups["blue"]["bank"])
    with state.lock:
        wars.end_war(war)
    assert (state.groups["red"]["bank"], state.groups["blue"]["bank"]) == banks
    adi.expect_text("tie")


def test_only_admins_declare_and_accept_and_not_twice(user):
    adi, ben = two_groups(user)
    cat = user("Cat")
    cat.line("/join Red")
    cat.expect(lambda m: m.get("type") == "history")
    cat.line("/war Blue")
    cat.expect_text("Only group admins", kind="error")
    adi.line("/war Red")
    adi.expect_text("your own group", kind="error")
    start_war(adi, ben)
    adi.line("/war Blue")
    adi.expect_text("already at war", kind="error")


def test_wars_end_by_themselves(user):
    adi, ben = two_groups(user)
    war = start_war(adi, ben)
    war["until"] = 0
    with state.lock:
        wars.end_due()
    assert state.wars == []
