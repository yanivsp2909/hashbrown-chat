"""🔴🟡 Connect 4 rules (games.py, no networking): drop pieces into columns 1-7, four in a row wins."""
import games


def play(game, *columns):
    """Players take turns dropping into these columns. Returns the last (ok, info)."""
    result = None
    for column in columns:
        result = game.move(game.turn, str(column))
    return result


def test_pieces_fall_to_the_bottom_and_turns_alternate():
    game = games.Connect4("adi", "ben")
    assert game.move("ben", "1") == (False, "⏳ Not your turn, wait for your opponent.")
    play(game, 4, 4)
    assert game.cells[5 * 7 + 3] == "🔴" and game.cells[4 * 7 + 3] == "🟡"
    assert game.turn == "adi"


def test_four_in_a_row_wins_across_down_and_diagonally():
    across = games.Connect4("adi", "ben")
    play(across, 1, 1, 2, 2, 3, 3, 4)
    assert across.finished and across.winner == "adi"
    down = games.Connect4("adi", "ben")
    play(down, 1, 2, 1, 2, 1, 2, 1)
    assert down.winner == "adi"
    diagonal = games.Connect4("adi", "ben")
    play(diagonal, 1, 2, 2, 3, 3, 4, 3, 4, 4, 7, 4)
    assert diagonal.winner == "adi"


def test_a_full_column_and_bad_input_are_refused():
    game = games.Connect4("adi", "ben")
    play(game, 1, 1, 1, 1, 1, 1)
    assert game.move(game.turn, "1") == (False, "That column is full.")
    assert game.move(game.turn, "8")[0] is False
    assert not game.looks_like_move("12") and game.looks_like_move(" 7 ")


def test_a_full_board_is_a_draw():
    game = games.Connect4("adi", "ben")
    order = [1, 2, 1, 2, 1, 2, 2, 1, 2, 1, 2, 1, 3, 4, 3, 4, 3, 4, 4, 3, 4, 3, 4, 3,
             5, 6, 5, 6, 5, 6, 6, 5, 6, 5, 6, 5, 7, 7, 7, 7, 7, 7]
    play(game, *order)
    assert game.finished and game.winner == "draw"


def test_state_and_render_for_each_player():
    game = games.Connect4("adi", "ben")
    play(game, 4)
    state = game.state("ben")
    assert state["game"] == "connect4" and state["you"] == "🟡" and state["your_turn"] is True
    assert len(state["cells"]) == 42
    assert "1️⃣" in game.render("adi") and "Opponent's turn" in game.render("adi")


def test_connect4_through_the_server(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben connect4")
    ben.expect_text("challenges you to 🔴🟡 Connect 4")
    ben.line("/accept Adi")
    board = adi.expect(lambda m: m.get("kind") == "board")
    assert board["state"]["game"] == "connect4"
