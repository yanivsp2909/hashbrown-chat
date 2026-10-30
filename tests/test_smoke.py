"""Smoke tests: the basics work end to end over real sockets."""
import json

import pytest

import server
from helpers import auth

pytestmark = pytest.mark.integration


def test_register_then_log_in_again(connect, user):
    adi = user("Adi")
    adi.line("/quit")
    assert adi.wait_closed()

    again = connect()
    result = auth(again, "login", "adi", "pass1234")
    assert result["ok"]
    assert result["text"] == "✅ Welcome back, Adi!"


def test_wrong_password_is_refused(connect, user):
    adi = user("Adi")
    adi.line("/quit")
    adi.wait_closed()
    result = auth(connect(), "login", "Adi", "wrong-pass")
    assert not result["ok"]


def test_account_is_saved_to_the_temp_data_file(user):
    user("Adi")
    with open(server.DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    assert "adi" in data["accounts"]


def test_chat_reaches_everyone_in_the_room(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("hello everyone")
    msg = ben.expect(lambda m: m.get("type") == "chat")
    assert (msg["name"], msg["text"]) == ("Adi", "hello everyone")


def test_give_moves_tokens(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/give Ben 30")
    adi.expect_text("You gave 30")
    ben.expect_text("gave you 30")
    assert server.accounts["adi"]["tokens"] == server.START_TOKENS - 30
    assert server.accounts["ben"]["tokens"] == server.START_TOKENS + 30


def start_game(a, b, game):
    """a challenges b, b accepts. Returns (first player, second player)."""
    a.line(f"/challenge {b.name} {game}")
    b.expect_text("challenges you to")
    b.line("/accept")
    a_board, b_board = a.expect_board(), b.expect_board()
    return (a, b) if a_board["state"]["your_turn"] else (b, a)


def play(first, second, moves):
    """Plays moves in turn, waiting until the next player is told it's their turn."""
    players = [first, second]
    for i, move in enumerate(moves):
        players[i % 2].line(move)
        if i < len(moves) - 1:
            players[(i + 1) % 2].expect_board(my_turn=True)


def test_full_tic_tac_toe_game(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben, "ttt")
    play(first, second, ["1", "4", "2", "5", "3"])  # first player gets the top row
    first.expect_text("🏆 YOU WON!", kind="money")
    second.expect_text("💀 You lost.", kind="error")
    winner = server.accounts[first.name.lower()]
    assert (winner["wins"], server.accounts[second.name.lower()]["losses"]) == (1, 1)
    assert first.name.lower() not in server.matches
