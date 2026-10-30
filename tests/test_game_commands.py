"""Game commands through the real server: /games, /challenge, /accept, /decline, /move, /board,
/resign and the solo Wordle (/wordle, /g, /giveup).

Money facts used below (see chatserver/config.py): everyone starts with 100 tokens, a win pays
the pot plus a 25 token reward, and the first win also unlocks an achievement (+50 tokens).
"""
import time

import pytest

from chatserver import config, state, textutil

pytestmark = pytest.mark.integration


def tokens(name):
    return state.accounts[name.lower()]["tokens"]


def start_game(a, b, game="ttt", bet=""):
    """a challenges b, b accepts. Returns (first player, second player)."""
    a.line(f"/challenge {b.name} {game} {bet}".strip())
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


# a fast ttt win for the first player: top row
FIRST_WINS = ["1", "4", "2", "5", "3"]
# a full draw (first player moves on even positions)
DRAW = list("123546879")


# ---------------------------------------------------------------- /games

def test_games_lists_every_game_and_wordle(user):
    adi = user("Adi")
    adi.line("/games")
    msg = adi.expect_text("Games", kind="game")
    for word in ("ttt", "damka", "math", "/wordle", "/challenge"):
        assert word in msg["text"]


# ---------------------------------------------------------------- /challenge refusals

def test_challenge_without_a_game_shows_usage(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben")
    adi.expect_text("Usage: /challenge", kind="error")


def test_challenge_someone_offline_is_refused(user):
    adi = user("Adi")
    adi.line("/challenge Nobody ttt")
    adi.expect_text("isn't online", kind="error")


def test_challenge_yourself_is_refused(user):
    adi = user("Adi")
    adi.line("/challenge Adi ttt")
    adi.expect_text("can't challenge yourself", kind="error")


def test_challenge_with_an_unknown_game_is_refused(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben chess")
    adi.expect_text("Games:", kind="error")
    assert "adi" not in {i["from"] for i in state.invites.get("ben", [])}


def test_challenge_someone_already_in_a_game_is_refused(user):
    adi, ben, cyn = user("Adi"), user("Ben"), user("Cyn")
    start_game(adi, ben)
    cyn.line("/challenge Adi ttt")
    cyn.expect_text("already in a game", kind="error")


def test_challenge_while_you_are_in_a_game_is_refused(user):
    adi, ben, cyn = user("Adi"), user("Ben"), user("Cyn")
    start_game(adi, ben)
    adi.line("/challenge Cyn ttt")
    adi.expect_text("already in a game", kind="error")


def test_bet_more_than_you_have_is_refused(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben ttt 500")
    adi.expect_text("You only have", kind="error")
    assert state.invites.get("ben", []) == []


def test_bet_the_opponent_cannot_afford_is_refused(user):
    adi, ben = user("Adi"), user("Ben")
    state.accounts["ben"]["tokens"] = 20
    adi.line("/challenge Ben ttt 50")
    adi.expect_text("Ben can't afford a 50", kind="error")
    assert state.invites.get("ben", []) == []


@pytest.mark.parametrize("bet", ["abc", "0", "-5"])
def test_nonsense_bet_is_refused(user, bet):
    adi, ben = user("Adi"), user("Ben")
    adi.line(f"/challenge Ben ttt {bet}")
    adi.expect_text("amount must be", kind="error")


def test_challenge_tells_both_players(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben damka 30")
    adi.expect_text("Challenge sent to Ben")
    msg = ben.expect_text("challenges you to", kind="event")
    assert "for 30" in msg["text"] and "/accept Adi" in msg["text"]


def test_new_challenge_from_the_same_person_replaces_the_old_one(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben ttt")
    adi.line("/challenge Ben math 10")
    adi.sync()
    invites = state.invites["ben"]
    assert len(invites) == 1 and invites[0]["bet"] == 10


# ---------------------------------------------------------------- /accept

def test_accept_starts_a_match_and_both_get_a_board(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben)
    assert state.matches["adi"] is state.matches["ben"]
    assert first.expect_board is not None  # both boards already arrived inside start_game
    assert state.invites["ben"] == []


def test_accept_with_a_bet_puts_both_bets_in_the_pot(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben ttt 40")
    ben.expect_text("challenges you to")
    ben.line("/accept")
    for p in (adi, ben):
        p.expect_text("pot: 80", kind="game")
    assert tokens("adi") == tokens("ben") == config.START_TOKENS - 40


def test_accept_with_nothing_waiting_says_so(user):
    ben = user("Ben")
    ben.line("/accept")
    ben.expect_text("No challenges waiting", kind="error")


def test_accept_by_name_picks_that_challenger(user):
    adi, ben, cyn = user("Adi"), user("Ben"), user("Cyn")
    adi.line("/challenge Cyn ttt")
    ben.line("/challenge Cyn ttt")
    cyn.expect_text("Ben challenges you")  # both have arrived
    cyn.line("/accept Adi")
    cyn.expect_board()
    assert set(state.matches) == {"adi", "cyn"}


def test_plain_accept_takes_the_newest_challenge(user):
    adi, ben, cyn = user("Adi"), user("Ben"), user("Cyn")
    adi.line("/challenge Cyn ttt")
    cyn.expect_text("Adi challenges you")
    ben.line("/challenge Cyn ttt")
    cyn.expect_text("Ben challenges you")
    cyn.line("/accept")
    cyn.expect_board()
    assert set(state.matches) == {"ben", "cyn"}


def test_accept_from_someone_who_did_not_challenge_is_refused(user):
    adi, ben, cyn = user("Adi"), user("Ben"), user("Cyn")
    adi.line("/challenge Ben ttt")
    ben.expect_text("challenges you")
    ben.line("/accept Cyn")
    ben.expect_text("No challenge from Cyn", kind="error")
    assert "ben" not in state.matches


def test_old_challenges_expire(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben ttt")
    ben.expect_text("challenges you")
    state.invites["ben"][0]["time"] = time.time() - 181
    ben.line("/accept")
    ben.expect_text("No challenges waiting", kind="error")


def test_accept_when_the_challenger_left_is_refused(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben ttt")
    ben.expect_text("challenges you")
    adi.line("/quit")
    assert adi.wait_closed()
    ben.line("/accept")
    ben.expect(lambda m: m.get("kind") == "error"
               and ("They left" in m["text"] or "No challenges" in m["text"]))
    assert "ben" not in state.matches


def test_accept_when_the_challenger_is_now_in_another_game_is_refused(user):
    adi, ben, cyn = user("Adi"), user("Ben"), user("Cyn")
    adi.line("/challenge Ben ttt")
    ben.expect_text("challenges you")
    start_game(adi, cyn)
    ben.line("/accept")
    ben.expect_text("already in a game", kind="error")
    assert state.matches["adi"] is state.matches["cyn"]


def test_accept_when_a_player_can_no_longer_afford_the_bet_is_refused(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben ttt 80")
    ben.expect_text("challenges you")
    state.accounts["adi"]["tokens"] = 10
    ben.line("/accept")
    ben.expect_text("can't afford the bet anymore", kind="error")
    assert tokens("adi") == 10 and tokens("ben") == config.START_TOKENS


# ---------------------------------------------------------------- /decline

def test_decline_tells_the_challenger(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben ttt")
    ben.expect_text("challenges you")
    ben.line("/decline")
    ben.expect_text("Declined")
    adi.expect_text("Ben declined your challenge", kind="error")
    assert state.matches == {} and state.invites["ben"] == []


def test_decline_by_name_keeps_the_other_challenge(user):
    adi, ben, cyn = user("Adi"), user("Ben"), user("Cyn")
    adi.line("/challenge Cyn ttt")
    ben.line("/challenge Cyn ttt")
    cyn.expect_text("Ben challenges you")
    cyn.line("/decline Adi")
    adi.expect_text("declined your challenge")
    cyn.line("/accept")
    cyn.expect_board()
    assert set(state.matches) == {"ben", "cyn"}


def test_decline_with_nothing_waiting_says_so(user):
    ben = user("Ben")
    ben.line("/decline")
    ben.expect_text("No challenges waiting", kind="error")


# ---------------------------------------------------------------- /board, /move

def test_board_shows_the_game_again(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben)
    first.line("/board")
    msg = first.expect_board()
    assert msg["state"]["game"] == "ttt"
    assert "Adi vs " in msg["text"] or " vs Adi" in msg["text"]


def test_board_without_a_game_is_refused(user):
    adi = user("Adi")
    adi.line("/board")
    adi.expect_text("not in a game", kind="error")


def test_move_command_works_like_typing_the_move(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben)
    first.line("/move 5")
    second.expect_board(my_turn=True)
    assert state.matches[first.name.lower()].game.cells[4] is not None


def test_move_without_a_game_is_refused(user):
    adi = user("Adi")
    adi.line("/move 5")
    adi.expect_text("not in a game", kind="error")


def test_move_out_of_turn_is_refused(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben)
    second.line("5")
    second.expect_text("Not your turn", kind="error")
    assert state.matches["adi"].game.cells == [None] * 9


def test_move_on_a_taken_square_is_refused(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben)
    play(first, second, ["5"])
    second.expect_board(my_turn=True)
    second.line("5")
    second.expect_text("taken", kind="error")


def test_a_chat_line_that_is_not_a_move_is_still_chat(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben)
    first.line("good luck!")
    msg = second.expect(lambda m: m.get("type") == "chat")
    assert msg["text"] == "good luck!"


def test_damka_illegal_move_is_refused_over_the_wire(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben, "damka")
    first.line("/move d4 e5")
    first.expect_text("don't have a piece on d4", kind="error")


def test_math_duel_first_to_three_wins(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/challenge Ben math")  # math boards have no "your_turn", so no start_game here
    ben.expect_text("challenges you")
    ben.line("/accept")
    adi.expect_board()
    ben.expect_board()
    for _ in range(3):
        adi.line(str(state.matches["adi"].game.answer))
        adi.expect_board()
    adi.expect_text("YOU WON", kind="money")
    ben.expect_text("You lost", kind="error")
    assert state.matches == {}


# ---------------------------------------------------------------- /resign and payouts

def test_resign_gives_the_other_player_the_win(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben)
    first.line("/resign")
    second.expect_text("YOU WON", kind="money")
    first.expect_text("You lost", kind="error")
    assert state.matches == {}
    assert state.accounts[second.name.lower()]["wins"] == 1
    assert state.accounts[first.name.lower()]["losses"] == 1


def test_resign_without_a_game_is_refused(user):
    adi = user("Adi")
    adi.line("/resign")
    adi.expect_text("not in a game", kind="error")


def test_early_resign_pays_the_pot_but_no_win_reward(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben, bet=40)
    first.line("/resign")
    msg = second.expect_text("YOU WON", kind="money")
    assert "+80" in msg["text"] and "win reward" not in msg["text"]
    assert tokens(first.name) == config.START_TOKENS - 40
    # pot back (100 - 40 + 80) plus the first-win achievement
    assert tokens(second.name) == config.START_TOKENS + 40 + config.ACHIEVEMENTS["first_win"][3]


def test_resign_after_both_really_played_still_earns_the_win_reward(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben)
    play(first, second, ["1", "4", "2", "5"])
    first.expect_board(my_turn=True)
    first.line("/resign")
    msg = second.expect_text("YOU WON", kind="money")
    assert f"+{config.WIN_REWARD} " in msg["text"] and "win reward" in msg["text"]


def test_finished_game_pays_pot_and_reward_to_the_winner(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben, bet=40)
    play(first, second, FIRST_WINS)
    msg = first.expect_text("YOU WON", kind="money")
    assert "+80" in msg["text"] and "win reward (1/" in msg["text"]
    second.expect_text("You lost", kind="error")
    assert tokens(second.name) == config.START_TOKENS - 40
    assert tokens(first.name) == (config.START_TOKENS - 40 + 80 + config.WIN_REWARD
                                  + config.ACHIEVEMENTS["first_win"][3])


def test_win_without_a_bet_has_reward_but_no_pot(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben)
    play(first, second, FIRST_WINS)
    msg = first.expect_text("YOU WON", kind="money")
    assert "pot" not in msg["text"] and "win reward" in msg["text"]


def test_win_reward_stops_after_the_daily_limit(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben)
    state.accounts[first.name.lower()].update(win_day=textutil.today(),
                                              rewarded_wins=config.MAX_REWARDED_WINS)
    play(first, second, FIRST_WINS)
    msg = first.expect_text("YOU WON", kind="money")
    assert "win reward" not in msg["text"]


def test_draw_refunds_the_bets(user):
    adi, ben = user("Adi"), user("Ben")
    first, second = start_game(adi, ben, bet=40)
    play(first, second, DRAW)
    for p in (first, second):
        p.expect_text("Draw", kind="game")
        assert tokens(p.name) == config.START_TOKENS
        assert state.accounts[p.name.lower()]["draws"] == 1
    assert state.matches == {}


def test_after_a_game_you_can_play_again(user):
    adi, ben = user("Adi"), user("Ben")
    first, _ = start_game(adi, ben)
    first.line("/resign")
    first.sync()
    start_game(adi, ben)
    assert state.matches["adi"] is state.matches["ben"]


def test_others_in_the_lobby_hear_who_won(user):
    adi, ben, cyn = user("Adi"), user("Ben"), user("Cyn")
    first, second = start_game(adi, ben, bet=40)
    first.line("/resign")
    cyn.expect_text(f"{second.name} beat {first.name} at", kind=None)


# ---------------------------------------------------------------- Wordle

def start_wordle(player, answer="apple"):
    """Starts Wordle and makes the secret word known."""
    player.line("/wordle")
    player.expect_board()
    state.solo[player.name.lower()].answer = answer


WRONG_WORDS = ["brave", "chair", "dance", "eagle", "flame", "grape"]


def test_wordle_starts_with_rules_and_an_empty_board(user):
    adi = user("Adi")
    adi.line("/wordle")
    msg = adi.expect_board()
    assert "rewarded games left today" in msg["text"]
    assert msg["state"]["guesses"] == [] and not msg["state"]["finished"]


def test_wordle_again_while_playing_continues_the_same_game(user):
    adi = user("Adi")
    start_wordle(adi)
    adi.line("/g brave")
    adi.expect_board()
    adi.line("/wordle")
    msg = adi.expect_board()
    assert "still going" in msg["text"] and len(msg["state"]["guesses"]) == 1
    assert state.solo["adi"].answer == "apple"


def test_wordle_after_the_daily_limit_says_no_more_rewards(user):
    adi = user("Adi")
    state.accounts["adi"].update(solo_day=textutil.today(), solo_rewarded=config.SOLO_MAX_REWARDS)
    adi.line("/wordle")
    assert "No more rewards today" in adi.expect_board()["text"]


def test_guess_before_starting_is_refused(user):
    adi = user("Adi")
    adi.line("/g crane")
    adi.expect_text("Start a game first", kind="error")


def test_guess_shows_the_colored_row(user):
    adi = user("Adi")
    start_wordle(adi)
    adi.line("/g alloy")
    msg = adi.expect_board()
    assert msg["state"]["guesses"][0]["colors"] == ["green", "yellow", "gray", "gray", "gray"]
    assert "Y" in msg["text"] and "Try 2/6" in msg["text"]


@pytest.mark.parametrize("word", ["abc", "abcdefg", "ab3de", ""])
def test_wrong_length_or_non_letters_are_refused(user, word):
    adi = user("Adi")
    start_wordle(adi)
    adi.line(f"/g {word}")
    adi.expect_text("5 English letters", kind="error")
    assert state.solo["adi"].guesses == []


def test_repeating_a_guess_is_refused(user):
    adi = user("Adi")
    start_wordle(adi)
    adi.line("/g brave")
    adi.expect_board()
    adi.line("/g brave")
    adi.expect_text("already tried", kind="error")


def test_correct_guess_pays_by_number_of_tries(user):
    adi = user("Adi")
    start_wordle(adi)
    for word in WRONG_WORDS[:3]:
        adi.line(f"/g {word}")
        adi.expect_board()
    adi.line("/g apple")
    msg = adi.expect_text("Solved in 4/6", kind="money")
    assert "+30" in msg["text"] and "1/" in msg["text"]
    assert "adi" not in state.solo
    account = state.accounts["adi"]
    assert account["solo_rewarded"] == 1
    # 4 tries = 30, plus the Wordsmith achievement; no Genius (needs 3 tries or less)
    assert account["tokens"] == config.START_TOKENS + 30 + config.ACHIEVEMENTS["wordsmith"][3]
    assert "genius" not in account["achievements"]


def test_solving_in_three_tries_unlocks_genius(user):
    adi = user("Adi")
    start_wordle(adi)
    for word in WRONG_WORDS[:2]:
        adi.line(f"/g {word}")
        adi.expect_board()
    adi.line("/g apple")
    adi.expect_text("Solved in 3/6", kind="money")
    adi.sync()
    assert {"wordsmith", "genius"} <= set(state.accounts["adi"]["achievements"])


def test_solved_wordle_is_shared_with_others_without_spoilers(user):
    adi, ben = user("Adi"), user("Ben")
    start_wordle(adi)
    adi.line("/g apple")
    msg = ben.expect_text("solved Wordle in 1/6")
    assert "🟩🟩🟩🟩🟩" in msg["text"] and "APPLE" not in msg["text"].upper().replace("🟩", "")


def test_no_token_reward_after_the_daily_limit(user):
    adi = user("Adi")
    state.accounts["adi"].update(solo_day=textutil.today(), solo_rewarded=config.SOLO_MAX_REWARDS)
    start_wordle(adi)
    adi.line("/g apple")
    adi.expect_text("No more token rewards today", kind="money")
    assert tokens("adi") == config.START_TOKENS + sum(
        config.ACHIEVEMENTS[a][3] for a in ("wordsmith", "genius"))


def test_daily_reward_counter_starts_over_on_a_new_day(user):
    adi = user("Adi")
    state.accounts["adi"].update(solo_day="2000-01-01", solo_rewarded=config.SOLO_MAX_REWARDS)
    start_wordle(adi)
    adi.line("/g apple")
    adi.expect_text("Solved in 1/6! +60", kind="money")
    assert state.accounts["adi"]["solo_rewarded"] == 1


def test_running_out_of_tries_ends_the_game_and_reveals_the_word(user):
    adi = user("Adi")
    start_wordle(adi)
    for word in WRONG_WORDS:
        adi.line(f"/g {word}")
        adi.expect_board()
    adi.expect_text("Out of tries! The word was APPLE", kind="error")
    assert "adi" not in state.solo
    assert tokens("adi") == config.START_TOKENS


def test_guess_after_the_game_ended_needs_a_new_game(user):
    adi = user("Adi")
    start_wordle(adi)
    adi.line("/g apple")
    adi.expect_text("Solved", kind="money")
    adi.line("/g brave")
    adi.expect_text("Start a game first", kind="error")


def test_giveup_reveals_the_word_and_ends_the_game(user):
    adi = user("Adi")
    start_wordle(adi, "mango")
    adi.line("/giveup")
    adi.expect_text("The word was MANGO")
    assert "adi" not in state.solo
    assert tokens("adi") == config.START_TOKENS


def test_giveup_without_a_game_is_refused(user):
    adi = user("Adi")
    adi.line("/giveup")
    adi.expect_text("not playing Wordle", kind="error")


def test_wordle_games_are_separate_per_player(user):
    adi, ben = user("Adi"), user("Ben")
    start_wordle(adi, "apple")
    start_wordle(ben, "mango")
    adi.line("/g apple")
    adi.expect_text("Solved", kind="money")
    assert "ben" in state.solo and "adi" not in state.solo
