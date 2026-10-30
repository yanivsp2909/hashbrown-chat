"""👀 Spectating: /watch name follows their match (read-only boards and the result); /watch alone stops."""
import pytest

import games
from chatserver import matches, state

pytestmark = pytest.mark.integration


def start(game_class=games.TicTacToe):
    with state.lock:
        matches.start_match(game_class, "adi", "ben", 0)
    return state.matches["adi"]


def board(client):
    return client.expect(lambda m: m.get("kind") == "board")


def test_watching_shows_the_board_and_tells_the_players(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    start()
    cat.line("/watch Adi")
    seen = board(cat)
    assert seen["state"]["spectating"] is True and seen["state"]["your_turn"] is False
    assert "👀" in seen["text"]
    adi.expect_text("👀 Cat is watching")


def test_spectators_follow_every_move_and_see_the_result(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    match = start()
    cat.line("/watch Ben")
    board(cat)
    mover = adi if match.game.turn == "adi" else ben
    mover.line("5")
    assert board(cat)["state"]["cells"][4] is not None
    adi.line("/resign")
    cat.expect_text("🏁")


def test_battleship_spectators_never_see_the_ships(user):
    _, _, cat = user("Adi"), user("Ben"), user("Cat")
    start(games.Battleship)
    cat.line("/watch Adi")
    seen = board(cat)["state"]
    assert "ship" not in seen["mine"] and "ship" not in seen["theirs"]


def test_you_cant_watch_someone_who_isnt_playing_or_yourself(user):
    adi, _, cat = user("Adi"), user("Ben"), user("Cat")
    cat.line("/watch Adi")
    cat.expect_text("isn't playing", kind="error")
    start()
    adi.line("/watch Adi")
    adi.expect_text("You're playing", kind="error")


def test_watch_alone_stops_watching(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    match = start()
    cat.line("/watch Adi")
    board(cat)
    cat.line("/watch")
    cat.expect_text("stopped watching")
    assert "cat" not in match.spectators
