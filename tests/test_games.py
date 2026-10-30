"""Unit tests for games.py (no sockets)."""
import pytest

import games

pytestmark = pytest.mark.unit

P1, P2 = "alice", "bob"


# ---------------------------------------------------------------- Tic-Tac-Toe

def play(game, moves):
    """moves: list of (player, text). Every move must be accepted."""
    for player, text in moves:
        ok, message = game.move(player, text)
        assert ok, message


def test_ttt_row_win():
    g = games.TicTacToe(P1, P2)
    play(g, [(P1, "1"), (P2, "4"), (P1, "2"), (P2, "5"), (P1, "3")])
    assert g.finished and g.winner == P1


def test_ttt_draw():
    g = games.TicTacToe(P1, P2)
    order = [P1, P2, P1, P2, P1, P2, P1, P2, P1]
    play(g, list(zip(order, "123546879")))
    assert g.finished and g.winner == "draw"


def test_ttt_taken_square_is_rejected_and_turn_stays():
    g = games.TicTacToe(P1, P2)
    play(g, [(P1, "1")])
    ok, message = g.move(P2, "1")
    assert not ok and "taken" in message
    assert g.turn == P2


def test_ttt_not_your_turn():
    g = games.TicTacToe(P1, P2)
    ok, message = g.move(P2, "1")
    assert not ok and "Not your turn" in message
    assert g.cells == [None] * 9


# ---------------------------------------------------------------- Damka

def empty_damka(pieces):
    """pieces: {"b6": "r", ...}. Red (P1) moves first."""
    g = games.Checkers(P1, P2)
    g.board = [[None] * 8 for _ in range(8)]
    for name, piece in pieces.items():
        r, c = g.square(name)
        g.board[r][c] = piece
    return g


def piece_at(g, name):
    r, c = g.square(name)
    return g.board[r][c]


def test_damka_mandatory_capture_rejects_quiet_move():
    g = empty_damka({"c3": "r", "h2": "r", "d4": "b", "a8": "b"})
    ok, message = g.move(P1, "h2 g3")
    assert not ok and "must capture" in message
    ok, _ = g.move(P1, "c3 e5")
    assert ok and piece_at(g, "d4") is None


def test_damka_multi_jump_must_continue_with_same_piece():
    g = empty_damka({"c3": "r", "h2": "r", "d4": "b", "f6": "b", "a8": "b"})
    ok, message = g.move(P1, "c3 e5")
    assert ok and "Jump again" in message
    assert g.turn == P1 and g.chain == g.square("e5")
    ok, message = g.move(P1, "h2 g3")
    assert not ok and "keep jumping" in message
    ok, _ = g.move(P1, "e5 g7")
    assert ok and g.turn == P2 and g.chain is None
    assert piece_at(g, "f6") is None


def test_damka_flying_king_moves_from_a_distance():
    g = empty_damka({"a1": "R", "h2": "b"})
    ok, message = g.move(P1, "a1 d4")
    assert ok, message
    assert piece_at(g, "d4") == "R"


def test_damka_flying_king_captures_from_a_distance():
    g = empty_damka({"a1": "R", "d4": "b", "a8": "b"})
    ok, message = g.move(P1, "a1 f6")
    assert ok, message
    assert piece_at(g, "d4") is None and piece_at(g, "f6") == "R"


def test_damka_man_keeps_jumping_through_last_row_and_is_not_crowned_yet():
    # G1: landing on the last row mid-capture does not crown or end the chain
    g = empty_damka({"b6": "r", "c7": "b", "e7": "b", "h2": "b"})
    ok, message = g.move(P1, "b6 d8")
    assert ok, message
    assert g.chain == g.square("d8") and g.turn == P1
    assert piece_at(g, "d8") == "r"
    ok, message = g.move(P1, "d8 f6")
    assert ok, message
    assert piece_at(g, "f6") == "r" and g.turn == P2 and g.chain is None
    assert piece_at(g, "c7") is None and piece_at(g, "e7") is None


def test_damka_sequence_ending_on_last_row_crowns():
    g = empty_damka({"b6": "r", "c7": "b", "h2": "b"})
    ok, message = g.move(P1, "b6 d8")
    assert ok, message
    assert piece_at(g, "d8") == "R"
    assert g.chain is None and g.turn == P2


def test_damka_plain_move_to_last_row_crowns():
    g = empty_damka({"b7": "r", "h2": "b"})
    ok, message = g.move(P1, "b7 a8")
    assert ok, message
    assert piece_at(g, "a8") == "R"


# ---------------------------------------------------------------- Math duel

def fixed_math(answer=2):
    g = games.MathDuel(P1, P2)
    g.question, g.answer = "1 + 1", answer
    return g


@pytest.mark.parametrize("text", ["²", "--5", "-", "", "  ", "1234567", "-1234567", "٣", "5.0", "1 2", "+5"])
def test_math_looks_like_move_rejects(text):
    g = fixed_math()
    assert not g.looks_like_move(text)
    ok, _ = g.move(P1, text)  # must not raise
    assert not ok


@pytest.mark.parametrize("text", ["5", "-5", " 42 ", "123456", "-123456", "0"])
def test_math_looks_like_move_accepts(text):
    assert fixed_math().looks_like_move(text)


def test_math_wrong_answer_locks_you_out():
    g = fixed_math()
    ok, message = g.move(P1, "5")
    assert not ok and "Wrong" in message
    ok, message = g.move(P1, "2")  # even the right answer is refused now
    assert not ok and "already missed" in message
    assert g.score[P1] == 0


def test_math_both_wrong_skips_question():
    g = fixed_math()
    g.move(P1, "5")
    ok, _ = g.move(P2, "6")
    assert ok
    assert g.asked == 2 and g.last[0] is None
    assert g.locked == set()


def test_math_first_to_three_wins():
    g = games.MathDuel(P1, P2)
    for _ in range(3):
        ok, _ = g.move(P1, str(g.answer))
        assert ok
    assert g.finished and g.winner == P1
    assert g.score[P1] == 3


# ---------------------------------------------------------------- Wordle

def test_wordle_double_letters():
    score = games.Wordle.score
    assert "".join(score("speed", "abide")) == "⬛⬛🟨⬛🟨"
    assert "".join(score("eerie", "there")) == "🟨⬛🟨⬛🟩"
    assert "".join(score("llama", "hello")) == "🟨🟨⬛⬛⬛"


WRONG_WORDS = ["brave", "chair", "dance", "eagle", "flame", "grape"]


@pytest.mark.parametrize("tries,reward", [(1, 60), (2, 50), (3, 40), (4, 30), (5, 20), (6, 10)])
def test_wordle_reward_by_tries(tries, reward):
    w = games.Wordle()
    w.answer = "apple"
    for word in WRONG_WORDS[:tries - 1] + ["apple"]:
        ok, message = w.guess(word)
        assert ok, message
    assert w.won and w.finished
    assert w.reward() == reward


def test_wordle_loss_pays_nothing():
    w = games.Wordle()
    w.answer = "apple"
    for word in WRONG_WORDS:
        w.guess(word)
    assert w.finished and not w.won
    assert w.reward() == 0
