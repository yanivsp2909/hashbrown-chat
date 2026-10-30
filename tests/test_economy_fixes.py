"""Bug fixes: token exploits, bets, Hashbrown charges and refunds (owner decisions D1-D3)."""
import random

import pytest

from chatserver import background, config, matches, state
from test_smoke import play, start_game

pytestmark = pytest.mark.integration


def give_tokens(name, amount):
    with state.lock:
        state.accounts[name.lower()]["tokens"] = amount


# ---------------------------------------------------------------- D1: at most 2 groups each

def test_a_person_can_own_at_most_two_groups(user):
    adi = user("Adi")
    give_tokens("Adi", 900)  # under 1000, so the 💰 Rich achievement doesn't add tokens
    for name in ("One", "Two"):
        adi.line(f"/create {name}")
        adi.expect_text("Created")
    adi.line("/create Three")
    adi.expect_text("at most 2 groups", kind="error")
    assert "three" not in state.groups
    assert state.accounts["adi"]["tokens"] == 900 - 2 * config.GROUP_COST + 50  # +50 founder, once


def test_disbanding_frees_a_group_slot(user):
    adi = user("Adi")
    give_tokens("Adi", 1000)
    for name in ("One", "Two"):
        adi.line(f"/create {name}")
        adi.expect_text("Created")
    adi.line("/disband")  # disbands Two, the room Adi is in
    adi.expect(lambda m: m.get("type") == "history")
    adi.line("/create Three")
    adi.expect_text("Created")


# ---------------------------------------------------------------- D2: Team Player needs 50+

def test_tiny_donation_does_not_unlock_team_player(user):
    adi = user("Adi")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    adi.line("/donate 1")
    adi.expect_text("donated 1")
    adi.sync()
    assert "team_player" not in state.accounts["adi"]["achievements"]


def test_donating_fifty_unlocks_team_player(user):
    adi = user("Adi")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    adi.line("/donate 50")
    adi.expect_text("ACHIEVEMENT UNLOCKED: 🤝")
    assert "team_player" in state.accounts["adi"]["achievements"]


# ---------------------------------------------------------------- D3: no win bonus for instant resigns

def test_no_win_bonus_when_the_loser_resigns_right_away(user):
    adi, ben = user("Adi"), user("Ben")
    start_game(adi, ben, "ttt")
    ben.line("/resign")
    adi.expect_text("🏆 YOU WON!", kind="money")
    assert state.accounts["adi"]["rewarded_wins"] == 0


def test_no_win_bonus_when_the_loser_disconnects_right_away(user):
    adi, ben = user("Adi"), user("Ben")
    start_game(adi, ben, "ttt")
    ben.line("/quit")
    adi.expect_text("🏆 YOU WON!", kind="money")
    assert state.accounts["adi"]["rewarded_wins"] == 0


def test_win_bonus_after_a_real_game_even_if_it_ends_by_resign(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben, "ttt")
    play(first, second, ["1", "4", "9", "5"])  # 2 moves each
    second.line("/resign")
    first.expect_text("🏆 YOU WON!", kind="money")
    assert state.accounts[first.name.lower()]["rewarded_wins"] == 1


def test_normal_wins_still_get_the_bonus(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben, "ttt")
    play(first, second, ["1", "4", "2", "5", "3"])
    first.expect_text("win reward", kind="money")


def test_pot_is_still_paid_on_an_instant_resign(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben ttt 40")
    ben.expect_text("challenges you to")
    ben.line("/accept")
    adi.expect_board()
    ben.line("/resign")
    adi.expect_text("🏆 YOU WON!", kind="money")
    assert state.accounts["adi"]["tokens"] >= config.START_TOKENS + 40


# ---------------------------------------------------------------- bets on shutdown

def test_bets_are_refunded_when_the_server_stops(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben ttt 40")
    ben.expect_text("challenges you to")
    ben.line("/accept")
    adi.expect_board()
    with state.lock:
        matches.end_all_matches()
        assert state.accounts["adi"]["tokens"] == config.START_TOKENS
        assert state.accounts["ben"]["tokens"] == config.START_TOKENS
        assert not state.matches


# ---------------------------------------------------------------- Hashbrown charges and refunds

def make_hashbrown_group(owner):
    owner.line("/create Potatoes")
    owner.expect_text("Created")
    with state.lock:
        state.groups["potatoes"]["upgrades"].append("hashbrown")
        state.groups["potatoes"]["bank"] = 300


def test_failed_question_is_refunded_to_the_owner_if_the_group_was_disbanded(user, fake_hashbrown):
    adi = user("Adi")
    make_hashbrown_group(adi)
    fake_hashbrown.delay, fake_hashbrown.status = 0.5, 500
    adi.line("@hashbrown hi")
    adi.expect_text("thinking")
    adi.line("/disband")  # the bank (280 now) goes to Adi
    adi.expect_text("went to you", kind="money")
    after_disband = state.accounts["adi"]["tokens"]
    adi.expect_text("refunded", timeout=5)
    assert state.accounts["adi"]["tokens"] == after_disband + config.HASHBROWN_COST


def test_failed_question_does_not_refund_a_new_group_with_the_same_name(user, fake_hashbrown):
    adi = user("Adi")
    give_tokens("Adi", 1000)
    make_hashbrown_group(adi)
    fake_hashbrown.delay, fake_hashbrown.status = 0.5, 500
    adi.line("@hashbrown hi")
    adi.expect_text("thinking")
    adi.line("/disband")
    adi.expect_text("went to you", kind="money")
    adi.line("/create Potatoes")  # a brand new group, same name
    adi.expect_text("Created")
    adi.expect_text("refunded", timeout=5)
    assert state.groups["potatoes"]["bank"] == 0


def test_answer_reaches_the_asker_if_the_room_is_gone(user, fake_hashbrown):
    adi = user("Adi")
    make_hashbrown_group(adi)
    fake_hashbrown.delay = 0.5
    adi.line("@hashbrown hi")
    adi.expect_text("thinking")
    adi.line("/disband")
    adi.expect_text(fake_hashbrown.answer, timeout=5)


def test_failed_question_does_not_use_up_a_daily_question(user, fake_hashbrown):
    adi = user("Adi")
    fake_hashbrown.status = 500
    adi.line("@hashbrown hi")
    adi.expect_text("refunded")
    assert state.hashbrown_today.get("adi", ("", 0))[1] == 0


# ---------------------------------------------------------------- small ones

def test_slots_jackpot_achievement_is_saved(user, monkeypatch):
    adi = user("Adi")
    monkeypatch.setattr(random, "choices", lambda symbols, k: ["🍒"] * 3)
    adi.line("/slots 10")
    adi.expect_text("ACHIEVEMENT UNLOCKED: 🎰")
    adi.sync()
    with open(config.DATA_FILE, encoding="utf-8") as f:
        assert "jackpot" in f.read()


def test_quiz_time_up_is_not_sent_to_a_stale_connection(user):
    adi = user("Adi")
    opened = background.quiz_open()
    assert opened is not None
    current, free = opened
    real = state.online["adi"]
    replacement = type("Other", (), {"say": lambda *a: None, "key": "adi", "room": "lobby"})()
    told = []
    real.say = lambda text, kind="system": told.append(text)
    with state.lock:
        state.online["adi"] = replacement  # Adi reconnected: `real` is now stale
    try:
        background.quiz_close(current, free)
    finally:
        with state.lock:
            state.online["adi"] = real
    assert told == []
