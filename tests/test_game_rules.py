"""Game rule edge cases (games.py only, no server, no sockets).

tests/test_games.py covers the main rules. This file covers the things players trip over:
bad input, moving the wrong piece, how a game ends, and what the boards show.
"""
import pytest

import games

pytestmark = pytest.mark.unit

P1, P2 = "alice", "bob"


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


# ---------------------------------------------------------------- Tic-Tac-Toe

@pytest.mark.parametrize("text", ["0", "10", "x", "", "12", "1 2"])
def test_ttt_bad_square_is_refused(text):
    g = games.TicTacToe(P1, P2)
    ok, message = g.move(P1, text)
    assert not ok and "1 to 9" in message
    assert g.cells == [None] * 9 and g.turn == P1


def test_ttt_board_tells_each_player_whose_turn_it_is():
    g = games.TicTacToe(P1, P2)
    assert "Your turn" in g.render(P1)
    assert "Opponent's turn" in g.render(P2)
    assert g.state(P1)["your_turn"] and not g.state(P2)["your_turn"]


def test_ttt_finished_board_has_no_turn_line_and_nobody_to_move():
    g = games.TicTacToe(P1, P2)
    for player, square in [(P1, "1"), (P2, "4"), (P1, "2"), (P2, "5"), (P1, "3")]:
        g.move(player, square)
    assert "turn" not in g.render(P1).lower()
    assert not g.state(P1)["your_turn"] and g.state(P1)["finished"]


# ---------------------------------------------------------------- Damka

def test_damka_new_game_has_twelve_pieces_each():
    g = games.Checkers(P1, P2)
    flat = [p for row in g.board for p in row]
    assert flat.count("r") == 12 and flat.count("b") == 12


def test_damka_not_your_turn():
    g = games.Checkers(P1, P2)
    ok, message = g.move(P2, "b6 a5")
    assert not ok and "Not your turn" in message


@pytest.mark.parametrize("text", ["c3", "c3 d4 e5", "z1 a1", "c9 d4", ""])
def test_damka_badly_typed_move_is_refused(text):
    g = games.Checkers(P1, P2)
    ok, message = g.move(P1, text)
    assert not ok and "like c3 d4" in message


def test_damka_cannot_move_an_empty_square_or_the_opponents_piece():
    g = games.Checkers(P1, P2)
    ok, message = g.move(P1, "d4 e5")  # empty
    assert not ok and "don't have a piece on d4" in message
    ok, message = g.move(P1, "a7 b6")  # a blue piece
    assert not ok and "don't have a piece on a7" in message


def test_damka_man_cannot_step_backwards_or_sideways():
    g = empty_damka({"d4": "r", "h8": "b"})
    for target in ("c3", "e3", "d5", "c4"):
        ok, message = g.move(P1, f"d4 {target}")
        assert not ok and "isn't allowed" in message
    assert g.turn == P1


def test_damka_cannot_step_onto_an_occupied_square():
    g = empty_damka({"d4": "r", "c5": "r", "h8": "b"})
    ok, message = g.move(P1, "d4 c5")
    assert not ok and "isn't allowed" in message


def test_damka_man_can_capture_backwards():
    g = empty_damka({"d4": "r", "c3": "b", "h8": "b"})
    ok, message = g.move(P1, "d4 b2")
    assert ok, message
    assert piece_at(g, "c3") is None and piece_at(g, "b2") == "r"


def test_damka_capture_error_lists_the_legal_captures():
    g = empty_damka({"c3": "r", "d4": "b", "h8": "b"})
    ok, message = g.move(P1, "c3 b4")
    assert not ok and "c3 e5" in message


def test_damka_cannot_jump_your_own_piece():
    g = empty_damka({"c3": "r", "d4": "r", "h8": "b"})
    ok, message = g.move(P1, "c3 e5")
    assert not ok and "isn't allowed" in message


def test_damka_capturing_the_last_piece_wins():
    g = empty_damka({"c3": "r", "d4": "b"})
    ok, _ = g.move(P1, "c3 e5")
    assert ok and g.finished and g.winner == P1
    assert not g.state(P2)["your_turn"]


def test_damka_blocking_every_move_wins():
    # blue's only man on a8 is stuck behind red men and has nothing to jump
    g = empty_damka({"a8": "b", "b7": "r", "c6": "r", "h2": "r"})
    ok, message = g.move(P1, "h2 g3")
    assert ok, message
    assert g.finished and g.winner == P1


def test_damka_sixty_quiet_moves_in_a_row_is_a_draw():
    g = empty_damka({"a1": "R", "h2": "B"})
    squares = {P1: ("a1", "b2"), P2: ("h2", "g1")}
    player = P1
    for i in range(games.Checkers.MAX_QUIET_MOVES):
        assert not g.finished
        a, b = squares[player]
        ok, message = g.move(player, f"{a} {b}")
        assert ok, message
        squares[player] = (b, a)
        player = P2 if player == P1 else P1
    assert g.finished and g.winner == "draw"


def test_damka_a_capture_restarts_the_quiet_move_count():
    g = empty_damka({"a1": "R", "c3": "r", "d4": "b", "h8": "B"})
    g.quiet = 40
    ok, _ = g.move(P1, "c3 e5")
    assert ok and g.quiet == 0


def test_damka_board_shows_the_jump_reminder_only_to_the_jumper():
    g = empty_damka({"c3": "r", "d4": "b", "f6": "b", "a8": "b"})
    g.move(P1, "c3 e5")
    assert "Keep jumping with e5" in g.render(P1)
    assert "Keep jumping" not in g.render(P2)
    assert g.state(P1)["must_jump_from"] == "e5"


def test_damka_board_tells_each_player_their_color_and_direction():
    g = games.Checkers(P1, P2)
    assert "moving up" in g.render(P1) and "moving down" in g.render(P2)
    assert g.state(P1)["you"] == "r" and g.state(P2)["you"] == "b"
    assert g.state(P1)["must_jump_from"] is None


def test_damka_blue_man_is_crowned_on_row_one():
    g = empty_damka({"b2": "b", "h8": "r"})
    g.turn = P2
    ok, message = g.move(P2, "b2 a1")
    assert ok, message
    assert piece_at(g, "a1") == "B"


# ---------------------------------------------------------------- Math duel

def fixed_math(answer=2):
    g = games.MathDuel(P1, P2)
    g.question, g.answer = "1 + 1", answer
    return g


def test_math_move_after_the_game_is_over_is_refused():
    g = fixed_math()
    g.finished = True
    ok, message = g.move(P1, "2")
    assert not ok and "over" in message


def test_math_right_answer_scores_and_asks_the_next_question():
    g = fixed_math()
    ok, _ = g.move(P1, " 2 ")
    assert ok and g.score == {P1: 1, P2: 0}
    assert g.asked == 2 and g.last == (P1, "1 + 1", 2)


def test_math_a_lockout_ends_when_the_next_question_comes():
    g = fixed_math()
    g.move(P1, "9")
    assert P1 in g.locked
    g.move(P2, "2")
    assert g.locked == set()


def test_math_question_limit_with_equal_scores_is_a_draw():
    g = fixed_math()
    g.asked = games.MathDuel.MAX_QUESTIONS
    g.score = {P1: 1, P2: 2}
    g.move(P1, "2")  # P1 scores: 2 - 2, then the game ends on the question limit
    assert g.finished and g.winner == "draw"


def test_math_question_limit_gives_the_win_to_whoever_leads():
    g = fixed_math()
    g.asked = games.MathDuel.MAX_QUESTIONS
    g.score = {P1: 0, P2: 1}
    g.move(P1, "9")
    g.move(P2, "9")  # both missed, game ends, P2 leads
    assert g.finished and g.winner == P2


def test_math_questions_always_have_whole_number_answers():
    for _ in range(200):
        g = games.MathDuel(P1, P2)
        a, op, b = g.question.split()
        a, b = int(a), int(b)
        expected = {"+": a + b, "-": a - b, "×": a * b, "÷": a // b}[op]
        assert g.answer == expected
        if op == "÷":
            assert a % b == 0
        assert g.answer >= 0


def test_math_board_tells_each_player_who_got_the_last_question():
    g = fixed_math()
    g.move(P1, "2")
    assert "You got it" in g.render(P1)
    assert "They got it first" in g.render(P2)
    assert g.state(P1)["last"]["scored"] == "you"
    assert g.state(P2)["last"]["scored"] == "them"


def test_math_board_when_nobody_got_it():
    g = fixed_math()
    g.move(P1, "9")
    g.move(P2, "9")
    assert "Nobody got it" in g.render(P1)
    assert g.state(P1)["last"]["scored"] == "nobody"


def test_math_state_shows_lockout_and_hides_question_when_finished():
    g = fixed_math()
    g.move(P1, "9")
    assert g.state(P1)["locked_out"] and not g.state(P2)["locked_out"]
    g.finished = True
    assert g.state(P1)["question"] is None
    assert "Question" not in g.render(P1)


# ---------------------------------------------------------------- Wordle

def wordle(answer="apple"):
    w = games.Wordle()
    w.answer = answer
    return w


@pytest.mark.parametrize("text", ["", "abcd", "abcdef", "ab1de", "ab de", "héllo", "crane!"])
def test_wordle_guess_must_be_five_english_letters(text):
    w = wordle()
    ok, message = w.guess(text)
    assert not ok and "5 English letters" in message
    assert w.guesses == []


def test_wordle_guess_ignores_case_and_spaces():
    w = wordle()
    ok, _ = w.guess("  APPLE ")
    assert ok and w.won


def test_wordle_same_guess_twice_is_refused_and_costs_no_try():
    w = wordle()
    w.guess("brave")
    ok, message = w.guess("BRAVE")
    assert not ok and "already tried" in message
    assert len(w.guesses) == 1


def test_wordle_no_guesses_after_the_game_is_over():
    w = wordle()
    w.guess("apple")
    ok, message = w.guess("brave")
    assert not ok and "over" in message


def test_wordle_all_colors():
    assert "".join(games.Wordle.score("alloy", "apple")) == "🟩🟨⬛⬛⬛"
    assert "".join(games.Wordle.score("apple", "apple")) == "🟩" * 5
    assert "".join(games.Wordle.score("zzzzz", "apple")) == "⬛" * 5


def test_wordle_sixth_wrong_guess_ends_the_game_as_a_loss():
    w = wordle()
    for word in ["brave", "chair", "dance", "eagle", "flame"]:
        w.guess(word)
        assert not w.finished
    w.guess("grape")
    assert w.finished and not w.won


def test_wordle_state_names_the_colors_for_the_website():
    w = wordle()
    w.guess("alloy")
    state = w.state()
    assert state["guesses"] == [{"word": "alloy",
                                 "colors": ["green", "yellow", "gray", "gray", "gray"]}]
    assert state["max_tries"] == 6 and not state["finished"]


def test_wordle_share_shows_colors_but_never_the_letters():
    w = wordle()
    w.guess("alloy")
    w.guess("apple")
    assert w.share() == "🟩🟨⬛⬛⬛\n" + "🟩" * 5
    assert "a" not in w.share().lower()


def test_wordle_board_lists_letters_known_to_be_absent():
    w = wordle()
    w.guess("zzzzz")
    board = w.render()
    assert "Not in the word: Z" in board
    assert "Try 2/6" in board
    assert board.count("⬜⬜⬜⬜⬜") == 5


def test_wordle_letter_found_elsewhere_is_not_listed_as_absent():
    w = wordle("apple")
    w.guess("alloy")  # the second l is gray, but l is in the word
    assert "L" not in w.render().split("Not in the word:")[-1]


def test_wordle_finished_board_has_no_try_prompt():
    w = wordle()
    w.guess("apple")
    assert "Try " not in w.render()


def test_wordle_word_list_is_usable():
    assert len(games.WORDS) > 100
    assert all(len(w) == 5 and w.isalpha() and w.islower() for w in games.WORDS)
