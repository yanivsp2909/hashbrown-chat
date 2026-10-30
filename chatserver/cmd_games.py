"""
🎮 Game commands (and 🟩 Wordle).
"""
import time

import games

from chatserver import achievements, config, matches, registry, rooms, state, storage, textutil


GAMES = {"ttt": games.TicTacToe, "tictactoe": games.TicTacToe,
         "checkers": games.Checkers, "damka": games.Checkers,
         "math": games.MathDuel, "mathduel": games.MathDuel}


@registry.command("/games", "/games", "what you can play", "🎮 Games")
def cmd_games(client, args):
    client.say("🎮 Games (1v1, optional token bet):\n"
               "  ❌⭕ ttt        Tic-Tac-Toe\n"
               "  🔴🔵 damka      Checkers (also: checkers)\n"
               "  ➗   math       Math duel: first to 3 right answers\n"
               "Challenge: /challenge name game [bet]   e.g.  /challenge Adi damka 100\n\n"
               "🟩 Solo: /wordle  guess the word, win up to 60 🪙", "game")


@registry.command("/challenge", "/challenge name game [bet]", "invite to a 1v1", "🎮 Games")
def cmd_challenge(client, args):
    parts = args.split()
    if len(parts) < 2:
        client.say("Usage: /challenge name game [bet]   games: ttt, damka, math", "error")
        return
    target = rooms.find_online(client, parts[0])
    if target is None:
        return
    game_class = GAMES.get(parts[1].lower())
    if game_class is None:
        client.say("❓ Games: ttt, damka (checkers), math", "error")
        return
    if target == client.key:
        client.say("🙃 You can't challenge yourself.", "error")
        return
    bet = 0
    if len(parts) > 2:
        bet = rooms.parse_amount(client, parts[2])
        if bet is None:
            return
    if client.key in state.matches or target in state.matches:
        client.say("⏳ One of you is already in a game.", "error")
        return
    if state.accounts[target]["tokens"] < bet:
        client.say(f"💸 {rooms.nick(target)} can't afford a {bet} 🪙 bet.", "error")
        return
    waiting = [i for i in state.invites.get(target, []) if i["from"] != client.key]
    waiting.append({"from": client.key, "game": game_class, "bet": bet, "time": time.time()})
    state.invites[target] = waiting
    stake = f" for {bet} 🪙" if bet else ""
    rooms.tell(target, f"⚔️ {rooms.shown(client.key)} challenges you to {game_class.title}{stake}!  "
                 f"/accept {rooms.nick(client.key)}  or  /decline {rooms.nick(client.key)}", "event")
    client.say(f"⚔️ Challenge sent to {rooms.shown(target)}. Waiting for them...")


def pick_invite(client, args):
    fresh = [i for i in state.invites.get(client.key, []) if time.time() - i["time"] < 180]
    state.invites[client.key] = fresh
    if not fresh:
        client.say("📭 No challenges waiting for you.", "error")
        return None
    if args.strip():
        invite = next((i for i in fresh if rooms.nick(i["from"]).lower() == args.strip().lower()), None)
        if invite is None:
            client.say(f"❓ No challenge from {args.strip()}.", "error")
            return None
    else:
        invite = fresh[-1]
    fresh.remove(invite)
    return invite


@registry.command("/accept", "/accept [name]", "accept a challenge", "🎮 Games")
def cmd_accept(client, args):
    invite = pick_invite(client, args)
    if invite is None:
        return
    challenger, bet = invite["from"], invite["bet"]
    if challenger not in state.online:
        client.say("😕 They left already.", "error")
        return
    if challenger in state.matches or client.key in state.matches:
        client.say("⏳ One of you is already in a game.", "error")
        return
    if state.accounts[challenger]["tokens"] < bet or state.accounts[client.key]["tokens"] < bet:
        client.say("💸 Someone can't afford the bet anymore.", "error")
        return
    matches.start_match(invite["game"], challenger, client.key, bet)


@registry.command("/decline", "/decline [name]", "say no to a challenge", "🎮 Games")
def cmd_decline(client, args):
    invite = pick_invite(client, args)
    if invite:
        client.say("👎 Declined.")
        rooms.tell(invite["from"], f"👎 {rooms.shown(client.key)} declined your challenge.", "error")


@registry.command("/move", "/move ...", "a move (or just type it)", "🎮 Games")
def cmd_move(client, args):
    matches.do_move(client, args)


@registry.command("/board", "/board", "show the board again", "🎮 Games")
def cmd_board(client, args):
    match = state.matches.get(client.key)
    if match is None:
        client.say("🎮 You're not in a game.", "error")
        return
    p1, p2 = match.players
    client.send({"type": "msg", "kind": "board", "state": match.game.state(client.key),
                 "text": f"{match.game.title}   {rooms.shown(p1)} vs {rooms.shown(p2)}\n"
                         f"{match.game.render(client.key)}"})


@registry.command("/resign", "/resign", "give up the game 🏳️", "🎮 Games")
def cmd_resign(client, args):
    match = state.matches.get(client.key)
    if match is None:
        client.say("🎮 You're not in a game.", "error")
        return
    matches.finish_match(match, match.opponent(client.key), f"{rooms.nick(client.key)} resigned 🏳️")


# ----- 🟩 Solo: Wordle

def send_wordle(client, game, text):
    client.send({"type": "msg", "kind": "board", "text": text, "state": game.state()})


@registry.command("/wordle", "/wordle", "solo word game, win tokens 🟩", "🎮 Games")
def cmd_wordle(client, args):
    game = state.solo.get(client.key)
    if game and not game.finished:
        send_wordle(client, game, f"{games.Wordle.title} (still going)\n{game.render()}")
        return
    state.solo[client.key] = game = games.Wordle()
    account = state.accounts[client.key]
    left = config.SOLO_MAX_REWARDS - (account["solo_rewarded"] if account["solo_day"] == textutil.today() else 0)
    prize = f"Win up to 60 🪙 ({left} rewarded games left today)" if left > 0 else \
        "No more rewards today, but you can still play for fun"
    send_wordle(client, game, f"{games.Wordle.title}\n📜 {games.Wordle.help}\n🪙 {prize}\n\n{game.render()}")


@registry.command("/g", "/g word", "guess in your Wordle", "🎮 Games")
def cmd_guess(client, args):
    game = state.solo.get(client.key)
    if game is None or game.finished:
        client.say("🟩 Start a game first: /wordle", "error")
        return
    ok, info = game.guess(args)
    if not ok:
        client.say(info, "error")
        return
    send_wordle(client, game, f"\n{game.render()}")
    if not game.finished:
        return
    del state.solo[client.key]
    if not game.won:
        client.say(f"💀 Out of tries! The word was {game.answer.upper()}.", "error")
        return
    account = state.accounts[client.key]
    tries = len(game.guesses)
    if account["solo_day"] != textutil.today():
        account["solo_day"], account["solo_rewarded"] = textutil.today(), 0
    if account["solo_rewarded"] < config.SOLO_MAX_REWARDS:
        account["solo_rewarded"] += 1
        account["tokens"] += game.reward()
        client.say(f"🎉 Solved in {tries}/6! +{game.reward()} 🪙 "
                   f"({account['solo_rewarded']}/{config.SOLO_MAX_REWARDS} rewarded today)", "money")
    else:
        client.say(f"🎉 Solved in {tries}/6! (No more token rewards today.)", "money")
    rooms.announce(f"🟩 {rooms.shown(client.key)} solved Wordle in {tries}/6!\n{game.share()}", exclude={client.key})
    achievements.unlock(client.key, "wordsmith")
    if tries <= 3:
        achievements.unlock(client.key, "genius")
    achievements.check_rich(client.key)
    storage.save_data()


@registry.command("/giveup", "/giveup", "quit your Wordle", "🎮 Games")
def cmd_giveup(client, args):
    game = state.solo.pop(client.key, None)
    if game is None:
        client.say("🟩 You're not playing Wordle.", "error")
        return
    client.say(f"🏳️ The word was {game.answer.upper()}.")
