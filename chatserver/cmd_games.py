"""
🎮 Game commands (and 🟩 Wordle).

Three files work together on games:
  games.py (next to server.py)  the rules and the board of each game, no networking
  chatserver/matches.py         a match between two people: turns, bets, paying the winner
  chatserver/cmd_games.py       this file: the /commands players type
To add a game: write its class in games.py, then add it to GAMES below.
"""
import time

import games

from chatserver import achievements, config, hashbrown_ai, matches, registry, rooms, state, storage, textutil


GAMES = {"ttt": games.TicTacToe, "tictactoe": games.TicTacToe,
         "checkers": games.Checkers, "damka": games.Checkers,
         "math": games.MathDuel, "mathduel": games.MathDuel,
         "connect4": games.Connect4, "c4": games.Connect4,
         "battleship": games.Battleship, "ships": games.Battleship}


@registry.command("/games", "/games", "what you can play", "🎮 Games")
def cmd_games(client, args):
    client.say("🎮 Games (1v1, optional token bet):\n"
               "  ❌⭕ ttt        Tic-Tac-Toe\n"
               "  🔴🔵 damka      Checkers (also: checkers)\n"
               "  ➗   math       Math duel: first to 3 right answers\n"
               "  🔴🟡 connect4   Connect 4: four in a row (also: c4)\n"
               "  🚢   battleship Battleship: sink their ships, fire like c3 (also: ships)\n"
               "Challenge: /challenge name game [bet]   e.g.  /challenge Adi damka 100\n\n"
               "🟩 Solo: /wordle  guess the word, win up to 60 🪙", "game")


@registry.command("/challenge", "/challenge name game [bet]", "invite to a 1v1", "🎮 Games")
def cmd_challenge(client, args):
    parts = args.split()
    if len(parts) < 2:
        client.say("Usage: /challenge name game [bet]   games: ttt, damka, math, connect4, battleship", "error")
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


LEADERBOARDS = {"elo": ("elo", "📈 ELO"), "wins": ("wins", "🏆 wins"), "tokens": ("tokens", "🪙 tokens")}


@registry.command("/watch", "/watch [name]", "watch someone's game 👀 (/watch alone: stop)", "🎮 Games")
def cmd_watch(client, args):
    for match in set(state.matches.values()):   # stop watching whatever you watched before
        match.spectators.discard(client.key)
    name = args.strip()
    if not name:
        client.say("👀 You stopped watching.")
        return
    target = rooms.find_online(client, name)
    if target is None:
        return
    if client.key in state.matches:
        client.say("👀 You're playing a game yourself!", "error")
        return
    match = state.matches.get(target)
    if match is None:
        client.say(f"👀 {rooms.nick(target)} isn't playing right now.", "error")
        return
    match.spectators.add(client.key)
    for player in match.players:
        rooms.tell(player, f"👀 {rooms.shown(client.key)} is watching your game.", "game")
    matches.show_to_spectator(match, client.key)


@registry.command("/leaderboard", "/leaderboard [elo|wins|tokens]", "the best players (ELO by default) 📈", "🎮 Games")
def cmd_leaderboard(client, args):
    field, label = LEADERBOARDS.get(args.strip().lower(), LEADERBOARDS["elo"])
    ranking = sorted(state.accounts, key=lambda k: state.accounts[k][field], reverse=True)
    rows = [f"  {i}. {rooms.shown(k)}  {state.accounts[k][field]}" for i, k in enumerate(ranking[:10], 1)]
    place = ranking.index(client.key) + 1
    client.say(f"🏆 Leaderboard: {label}\n" + "\n".join(rows) + f"\nYou are #{place} of {len(ranking)}.")


@registry.command("/hint", "/hint", f"a Wordle hint from Hashbrown, one per game ({config.HASHBROWN_COST} 🪙)",
                  "🎮 Games")
def cmd_hint(client, args):
    game = state.solo.get(client.key)
    if game is None or game.finished:
        client.say("🟩 Start a /wordle first.", "error")
        return
    if getattr(game, "hinted", False):
        client.say("🟩 Only one hint per game!", "error")
        return
    if state.hashbrown is None:   # no AI: show one letter that isn't green yet
        game.hinted = True
        found = {i for word, colors in game.guesses for i, color in enumerate(colors) if color == "🟩"}
        place = next((i for i in range(len(game.answer)) if i not in found), 0)
        client.say(f"💡 Hint: letter {place + 1} is {game.answer[place].upper()}")
        return
    # Only used up once Hashbrown takes the question (not on a cooldown, no tokens...)
    game.hinted = hashbrown_ai.ask_hashbrown(client, config.HINT_QUESTION.format(word=game.answer), private=True,
                                             forbidden=game.answer)


@registry.command("/rematch", "/rematch", "challenge your last opponent again 🔁", "🎮 Games")
def cmd_rematch(client, args):
    last = state.last_match.get(client.key)
    if last is None:
        client.say("🔁 No game to rematch yet. /challenge someone!", "error")
        return
    opponent, game_class, bet = last
    game_name = next(name for name, cls in GAMES.items() if cls is game_class)
    cmd_challenge(client, f"{rooms.nick(opponent)} {game_name} {bet}" if bet else f"{rooms.nick(opponent)} {game_name}")


@registry.command("/claim", "/claim", f"win if the other player hasn't moved for {config.CLAIM_AFTER // 60} min ⏰",
                  "🎮 Games")
def cmd_claim(client, args):
    match = state.matches.get(client.key)
    if match is None:
        client.say("🎮 You're not in a game.", "error")
        return
    turn = getattr(match.game, "turn", None)
    if turn is None:
        client.say("⏰ This game has no turns to wait for (you both play at once).", "error")
        return
    if turn == client.key:
        client.say("⏰ It's your turn! You can only claim while the other player is thinking.", "error")
        return
    wait = int(config.CLAIM_AFTER - (time.monotonic() - match.last_move)) + 1
    if wait > 0:
        client.say(f"⏰ You can /claim in {wait} s if {rooms.nick(turn)} still hasn't moved.", "error")
        return
    matches.finish_match(match, client.key, f"{rooms.nick(turn)} didn't move for {config.CLAIM_AFTER // 60} min ⏰")


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
