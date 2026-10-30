"""🔁 /rematch (play the same person again, same game and bet) and ⏰ /claim (win when the other player
stopped moving on their turn)."""
import time

import pytest

import games
from chatserver import config, matches, state

pytestmark = pytest.mark.integration


def start(game_class=games.TicTacToe, bet=10):
    with state.lock:
        matches.start_match(game_class, "adi", "ben", bet)
    return state.matches["adi"]


def test_rematch_challenges_the_same_person_to_the_same_game_and_bet(user):
    adi, ben = user("Adi"), user("Ben")
    start()
    adi.line("/resign")
    ben.expect_text("YOU WON")
    ben.line("/rematch")
    invite = adi.expect_text("challenges you to")["text"]
    assert "Tic-Tac-Toe" in invite and "10" in invite
    adi.line("/accept Ben")
    adi.expect(lambda m: m.get("kind") == "board")
    assert state.matches["adi"] is state.matches["ben"]


def test_rematch_without_a_finished_game_is_refused(user):
    adi = user("Adi")
    adi.line("/rematch")
    adi.expect_text("No game to rematch", kind="error")


def test_claim_wins_when_the_other_player_stopped_moving_on_their_turn(user):
    adi, ben = user("Adi"), user("Ben")
    match = start(bet=0)
    waiting = match.opponent(match.game.turn)            # the player who is waiting for a move
    match.last_move = time.monotonic() - config.CLAIM_AFTER - 1
    claimer = adi if waiting == "adi" else ben
    claimer.line("/claim")
    claimer.expect_text("YOU WON")
    assert "adi" not in state.matches


def test_claim_too_early_says_how_long_to_wait(user):
    adi, ben = user("Adi"), user("Ben")
    match = start(bet=0)
    waiting = match.opponent(match.game.turn)
    claimer = adi if waiting == "adi" else ben
    claimer.line("/claim")
    claimer.expect_text("You can /claim in", kind="error")
    assert state.matches["adi"] is match


def test_you_cant_claim_on_your_own_turn(user):
    adi, ben = user("Adi"), user("Ben")
    match = start(bet=0)
    match.last_move = time.monotonic() - config.CLAIM_AFTER - 1
    mover = adi if match.game.turn == "adi" else ben
    mover.line("/claim")
    mover.expect_text("It's your turn", kind="error")


def test_math_duel_has_no_turns_to_claim(user):
    adi, _ = user("Adi"), user("Ben")
    start(games.MathDuel, bet=0)
    adi.line("/claim")
    adi.expect_text("no turns", kind="error")
