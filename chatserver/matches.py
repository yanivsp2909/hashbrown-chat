"""
🎮 Two-player matches: starting, moving, finishing and paying out.
"""
import random
import time

from chatserver import achievements, config, rooms, state, storage, textutil



# Functions to call after every finished match, like Hashbrown's game commentator (hashbrown_extras adds it):
# the match code doesn't need to know about the AI.
finish_hooks = []


class Match:
    def __init__(self, game_class, p1, p2, bet):
        first, second = random.sample([p1, p2], 2)  # random player goes first
        self.game = game_class(first, second)
        self.players = [first, second]
        self.bet = bet
        self.over = False
        self.moves = {first: 0, second: 0}  # accepted moves per player
        self.last_move = time.monotonic()    # for /claim: when the last move (or the start) happened
        self.spectators = set()              # 👀 logins watching this match (/watch)

    def opponent(self, key):
        return self.players[1] if key == self.players[0] else self.players[0]


def push_board(match, note=""):
    p1, p2 = match.players
    header = f"{match.game.title}   {rooms.shown(p1)} vs {rooms.shown(p2)}"
    for p in match.players:
        if p in state.online:
            text = f"\n{header}\n{match.game.render(p)}" + (f"\n{note}" if note else "")
            # "state" is the board as data: the terminal ignores it, the website draws it
            state.online[p].send({"type": "msg", "kind": "board", "text": text, "state": match.game.state(p)})
    for watcher in match.spectators:
        show_to_spectator(match, watcher, note)


def show_to_spectator(match, watcher, note=""):
    if watcher in state.online:
        p1, p2 = match.players
        text = (f"\n👀 {match.game.title}   {rooms.shown(p1)} vs {rooms.shown(p2)}\n{spectator_render(match.game)}"
                + (f"\n{note}" if note else ""))
        state.online[watcher].send({"type": "msg", "kind": "board", "text": text, "state": spectator_state(match.game)})


def spectator_state(game):
    """👀 The board for someone watching: what nobody has to hide (Battleship: hits and misses only)."""
    if hasattr(game, "spectator_state"):
        return game.spectator_state()
    return {**game.state(game.players[0]), "your_turn": False, "spectating": True}


def spectator_render(game):
    if hasattr(game, "spectator_render"):
        return game.spectator_render()
    return game.render(game.players[0]).rsplit("\n", 1)[0]   # without "your turn" (that's for player 1)


def was_played(match):
    """A real game: it ended by itself, or both made MIN_MOVES_FOR_BONUS moves (not an instant resign).
    Only real games pay the win bonus, move ELO and score war points, so they can't be farmed."""
    return match.game.finished or min(match.moves.values()) >= config.MIN_MOVES_FOR_BONUS


def stop_watching(key):
    """👀 Stop watching any match (you started your own, or you left)."""
    for match in set(state.matches.values()):
        match.spectators.discard(key)


def start_match(game_class, p1, p2, bet):
    stop_watching(p1)
    stop_watching(p2)
    match = Match(game_class, p1, p2, bet)
    for p in (p1, p2):
        state.accounts[p]["tokens"] -= bet  # both bets go into the pot
    state.matches[p1] = state.matches[p2] = match
    pot = f"   💰 pot: {bet * 2} 🪙" if bet else ""
    for p in match.players:
        rooms.tell(p, f"🎮 {game_class.title}: {rooms.shown(p1)} vs {rooms.shown(p2)}{pot}\n"
                      f"📜 {game_class.help}\n🏳️ /resign to give up", "game")
    push_board(match)


def finish_match(match, winner, reason=""):
    if match.over:
        return
    match.over = True
    for p in match.players:
        state.matches.pop(p, None)
        state.last_match[p] = (match.opponent(p), type(match.game), match.bet)   # for /rematch
    p1, p2 = match.players
    title = match.game.title
    reason = f" ({reason})" if reason else ""
    if winner == "draw" or winner is None:
        for p in match.players:
            state.accounts[p]["tokens"] += match.bet
            state.accounts[p]["draws"] += 1
            rooms.tell(p, f"🤝 Draw!{reason}" + (" Bets refunded." if match.bet else ""), "game")
    else:
        loser = match.opponent(winner)
        account = state.accounts[winner]
        pot = match.bet * 2
        account["tokens"] += pot
        account["wins"] += 1
        state.accounts[loser]["losses"] += 1
        # Free reward for winning, capped per day so two friends can't farm each other.
        # A resign or disconnect before both really played earns no reward (only the pot).
        if account["win_day"] != textutil.today():
            account["win_day"], account["rewarded_wins"] = textutil.today(), 0
        really_played = was_played(match)
        bonus = ""
        if really_played and account["rewarded_wins"] < config.MAX_REWARDED_WINS:
            account["rewarded_wins"] += 1
            account["tokens"] += config.WIN_REWARD
            bonus = (f" +{config.WIN_REWARD} 🪙 win reward "
                     f"({account['rewarded_wins']}/{config.MAX_REWARDED_WINS} today)")
        rooms.tell(winner, f"🏆 YOU WON!{reason}" + (f" +{pot} 🪙 pot" if pot else "") + bonus, "money")
        rooms.tell(loser, f"💀 You lost.{reason}", "error")
        prize = f" and took {pot} 🪙" if pot else ""
        rooms.announce(f"🏆 {rooms.shown(winner)} beat {rooms.shown(loser)} at {title}{prize}!", exclude={p1, p2})
        achievements.unlock(winner, "first_win")
        if account["wins"] >= 10:
            achievements.unlock(winner, "ten_wins")
        achievements.check_rich(winner)
    if was_played(match):
        update_elo(match, winner)
    outcome = "a draw" if winner in ("draw", None) else f"{rooms.nick(winner)} won"
    for watcher in match.spectators:
        rooms.tell(watcher, f"🏁 {title}: {rooms.nick(p1)} vs {rooms.nick(p2)}, {outcome}{reason}", "game")
    storage.save_data()
    for hook in finish_hooks:
        hook(match, winner)


def update_elo(match, winner):
    """📈 ELO: you gain more for beating a stronger player, and lose less to one. A draw counts as half a win.
    expected = 1 / (1 + 10 ** ((their rating - your rating) / 400)); change = K * (result - expected)."""
    p1, p2 = match.players
    r1, r2 = state.accounts[p1]["elo"], state.accounts[p2]["elo"]
    expected1 = 1 / (1 + 10 ** ((r2 - r1) / 400))
    result1 = 0.5 if winner in ("draw", None) else (1.0 if winner == p1 else 0.0)
    change = round(config.ELO_K * (result1 - expected1))
    for player, delta in ((p1, change), (p2, -change)):
        state.accounts[player]["elo"] += delta
        rooms.tell(player, f"📈 ELO: {state.accounts[player]['elo']} ({delta:+d})", "game")


def end_all_matches():
    """The server is stopping: cancel every running game and give the bets back."""
    for match in set(state.matches.values()):
        match.over = True
        for p in match.players:
            state.matches.pop(p, None)
            state.accounts[p]["tokens"] += match.bet
            rooms.tell(p, "🛑 The server is stopping, so your game was cancelled."
                       + (" Your bet was refunded." if match.bet else ""), "game")


def do_move(client, text):
    match = state.matches.get(client.key)
    if match is None:
        client.say("🎮 You're not in a game. /challenge someone!", "error")
        return
    ok, info = match.game.move(client.key, text)
    if not ok:
        client.say(info, "error")
        return
    match.moves[client.key] += 1
    match.last_move = time.monotonic()
    push_board(match, info)
    if match.game.finished:
        finish_match(match, match.game.winner)


def is_game_move(client, text):
    match = state.matches.get(client.key)
    return bool(match) and not text.startswith("/") and match.game.looks_like_move(text)
