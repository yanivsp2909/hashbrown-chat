"""📈 ELO ratings: everyone starts at 1000; beating a stronger player gains more than beating a weaker one."""
import json

import pytest

import games
from chatserver import config, matches, state, storage

pytestmark = pytest.mark.integration


def play_and_resign(loser_client, winner_name="ben"):
    with state.lock:
        matches.start_match(games.TicTacToe, "adi", "ben", 0)
    loser_client.line("/resign")


def test_new_accounts_start_at_1000_and_old_saves_get_it_too(tmp_path, monkeypatch):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"accounts": {"zed": {"login": "Zed", "nick": "Zed", "salt": "00", "password": "00",
                                                     "tokens": 5}}, "groups": {}}), encoding="utf-8")
    monkeypatch.setattr(config, "DATA_FILE", str(path))
    assert storage.load_data()
    assert state.accounts["zed"]["elo"] == config.START_ELO == 1000
    assert storage.new_account("Amy", "salt", "hash")["elo"] == 1000


def test_a_win_moves_both_ratings_by_the_same_amount(user):
    adi, ben = user("Adi"), user("Ben")
    play_and_resign(adi)
    ben.expect_text("📈 ELO")
    assert state.accounts["ben"]["elo"] == 1016 and state.accounts["adi"]["elo"] == 984


def test_beating_a_stronger_player_gains_more(user):
    adi, ben = user("Adi"), user("Ben")
    state.accounts["adi"]["elo"] = 1400
    play_and_resign(adi)
    ben.expect_text("📈 ELO")
    assert state.accounts["ben"]["elo"] - 1000 > 16


def test_a_draw_between_equals_changes_nothing(user):
    adi, ben = user("Adi"), user("Ben")
    with state.lock:
        match = matches.start_match(games.TicTacToe, "adi", "ben", 0) or state.matches["adi"]
        matches.finish_match(match, "draw")
    assert state.accounts["adi"]["elo"] == state.accounts["ben"]["elo"] == 1000


def test_the_leaderboard_ranks_by_elo_and_shows_your_place(user):
    adi, ben = user("Adi"), user("Ben")
    state.accounts["ben"]["elo"] = 1100
    adi.line("/leaderboard")
    board = adi.expect_text("🏆 Leaderboard")["text"]
    assert board.index("Ben") < board.index("Adi") and "1100" in board and "You are #2" in board


def test_the_leaderboard_can_sort_by_wins(user):
    adi, _ = user("Adi"), user("Ben")
    state.accounts["adi"]["wins"] = 7
    adi.line("/leaderboard wins")
    board = adi.expect_text("🏆 Leaderboard")["text"]
    assert "wins" in board and board.index("Adi") < board.index("Ben")


def test_whois_shows_the_rating(user):
    adi, _ = user("Adi"), user("Ben")
    adi.line("/whois Ben")
    assert "📈 ELO 1000" in adi.expect_text("👤")["text"]
