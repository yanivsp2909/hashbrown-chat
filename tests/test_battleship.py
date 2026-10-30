"""🚢 Battleship rules (games.py): a 6x6 sea each, ships placed for you, fire with a letter and a number."""
import games


def game_with_ships():
    game = games.Battleship("adi", "ben")
    game.ships = {"adi": [{(0, 0), (0, 1)}], "ben": [{(2, 2), (2, 3)}, {(5, 5)}]}   # (row, col)
    return game


def test_ships_are_placed_without_overlapping_and_inside_the_sea():
    game = games.Battleship("adi", "ben")
    for player in ("adi", "ben"):
        cells = [cell for ship in game.ships[player] for cell in ship]
        assert len(cells) == len(set(cells)) == sum(games.Battleship.SHIPS)
        assert all(0 <= r < 6 and 0 <= c < 6 for r, c in cells)


def test_hits_misses_and_sinking():
    game = game_with_ships()
    assert game.move("adi", "c3") == (True, "💥 Hit!")
    assert game.move("ben", "f6") == (True, "🌊 Miss.")
    assert game.move("adi", "c3") == (False, "You already fired at C3.")
    assert game.move("adi", "c4") == (True, "💥 Sunk!")
    assert not game.finished


def test_sinking_every_ship_wins():
    game = game_with_ships()
    for shot, reply in (("c3", "a1"), ("c4", "a2"), ("f6", None)):
        game.move("adi", shot)
        if reply:
            game.move("ben", reply if shot != "c4" else "f1")
    assert game.finished and game.winner == "adi"


def test_turns_and_bad_coordinates():
    game = game_with_ships()
    assert game.move("ben", "a1")[0] is False                 # not ben's turn
    assert game.move("adi", "g1")[0] is False and game.move("adi", "a7")[0] is False
    assert game.looks_like_move(" B5 ") and not game.looks_like_move("b55")


def test_you_see_your_ships_but_never_theirs():
    game = game_with_ships()
    game.move("adi", "c3")
    adi_view, ben_view = game.state("adi"), game.state("ben")
    assert adi_view["theirs"][2 * 6 + 2] == "hit" and adi_view["theirs"][2 * 6 + 3] is None   # unhit ship stays hidden
    assert ben_view["mine"][2 * 6 + 3] == "ship" and ben_view["mine"][2 * 6 + 2] == "hit"
    assert "🚢" not in game.render("adi").split("Their sea")[1]


def test_battleship_through_the_server(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben battleship")
    ben.expect_text("challenges you to 🚢 Battleship")
    ben.line("/accept Adi")
    board = adi.expect(lambda m: m.get("kind") == "board")
    assert board["state"]["game"] == "battleship" and "ship" not in board["state"]["theirs"]
