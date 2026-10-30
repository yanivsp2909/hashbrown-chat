"""
🎨 The drawing game (like Pictionary). /draw starts a round in your room: you get a secret word (only you) and
draw it on the website's canvas; the others guess in the chat. Every brush stroke is one small packet:

    drawer -> server: {"type": "stroke", "points": [[x, y], ...] (0-1000), "color": 0-7, "size": 1-3}
                      {"type": "stroke", "clear": true}                    (wipe the canvas)
    server -> room:   the same with "by", to clients that said "draw" at login
    server -> room:   {"type": "draw_round", "state": "started" | "ended", "drawer", "letters", "seconds",
                       "strokes" (the drawing so far, for someone who comes in), "word" (only when it ended)}

The server checks the guesses, so the word never reaches the guessers before the end: a right guess is never
posted. The first one wins DRAW_GUESS_PRIZE, the drawer DRAW_DRAWER_PRIZE. Old clients get the text lines.
"""
import random
import time

from chatserver import achievements, config, rooms, state

WORDS = ("cat", "dog", "pizza", "house", "tree", "sun", "fish", "car", "robot", "potato", "fries", "rocket",
         "guitar", "snake", "apple", "phone", "ghost", "crown", "cake", "boat", "bird", "flower", "train", "moon",
         "spider", "castle", "dragon", "ice cream", "football", "rainbow", "pirate", "penguin", "volcano", "camel")


def normalize(text):
    return " ".join(text.lower().split())


def start(client, args):
    room = client.room
    if args.strip().lower() == "stop":
        return give_up(client)
    if room in state.drawings:
        client.say(f"🎨 {rooms.nick(state.drawings[room]['drawer'])} is already drawing here. Guess!", "error")
        return
    here = [k for k, c in state.online.items() if c.room == room]
    if len(here) < 2:
        client.say("🎨 You need at least 2 people in the room to play.", "error")
        return
    word = random.choice(WORDS)
    state.drawings[room] = {"drawer": client.key, "word": word, "until": time.time() + config.DRAW_SECONDS,
                            "strokes": [], "stroke_times": []}
    client.say(f"🎨 Your word: {word.upper()}. Draw it! Don't write it. (/draw stop gives up)", "private")
    rooms.notify_room(room, f"🎨 {rooms.shown(client.key)} is drawing! Guess the word in the chat "
                            f"({len(word)} letters{', with a space' if ' ' in word else ''}). "
                            f"{config.DRAW_SECONDS} seconds.", kind="event")
    send_round(room)


def round_packet(room, ended=False, word=None):
    game = state.drawings.get(room)
    packet = {"type": "draw_round", "state": "ended" if ended else "started", "room": room}
    if game:
        packet.update({"drawer": rooms.nick(game["drawer"]), "letters": len(game["word"]),
                       "seconds": max(0, int(game["until"] - time.time())), "strokes": list(game["strokes"])})
    if word:
        packet["word"] = word
    return packet


def send_round(room, packet=None, only=None):
    packet = packet or round_packet(room)
    for c in [only] if only else list(state.online.values()):
        if c is not None and c.room == room and "draw" in c.features:
            c.send(packet)


def on_enter(client):
    """Someone came into a room with a round going: they get the drawing so far."""
    if client.room in state.drawings and "draw" in client.features:
        client.send(round_packet(client.room))


def valid_stroke(msg):
    """A clean copy of a stroke packet, or None if anything about it is off."""
    if msg.get("clear") is True:
        return {"clear": True}
    points, color, size = msg.get("points"), msg.get("color"), msg.get("size")
    if not isinstance(points, list) or not 1 <= len(points) <= config.DRAW_POINTS_MAX:
        return None
    clean = []
    for point in points:
        if (not isinstance(point, list) or len(point) != 2
                or not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 1000 for v in point)):
            return None
        clean.append(point)
    if not isinstance(color, int) or isinstance(color, bool) or not 0 <= color < 8:
        return None
    if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 3:
        return None
    return {"points": clean, "color": color, "size": size}


def stroke(client, msg):
    """A brush stroke from the drawer (anyone else's is dropped), passed on to the room."""
    game = state.drawings.get(client.room)
    if game is None or game["drawer"] != client.key:
        return
    now = time.time()
    game["stroke_times"] = [t for t in game["stroke_times"] if now - t < 1] + [now]
    if len(game["stroke_times"]) > config.DRAW_STROKES_PER_SECOND:
        return   # too fast: dropped (it doesn't count as spam, it just doesn't go out)
    clean = valid_stroke(msg)
    if clean is None:
        return
    game["strokes"] = [] if clean.get("clear") else (game["strokes"] + [clean])[-config.DRAW_STROKES_KEPT:]
    packet = {"type": "stroke", **clean, "by": rooms.nick(client.key)}
    for c in list(state.online.values()):
        if c is not client and c.room == client.room and "draw" in c.features:
            c.send(packet)


def check_guess(client, text):
    """Called before a chat line is posted. True if it was about the drawing (and must NOT be posted)."""
    game = state.drawings.get(client.room)
    if game is None or normalize(text) != normalize(game["word"]):
        return False
    if client.key == game["drawer"]:
        client.say("🎨 Don't say the word! Draw it.", "error")
        return True
    room, word = client.room, game["word"]
    state.accounts[client.key]["tokens"] += config.DRAW_GUESS_PRIZE
    state.accounts[game["drawer"]]["tokens"] += config.DRAW_DRAWER_PRIZE
    achievements.check_rich(client.key)
    finish(room, f"🎉 {rooms.shown(client.key)} guessed it: {word.upper()}! +{config.DRAW_GUESS_PRIZE} 🪙 "
                 f"({rooms.nick(game['drawer'])} +{config.DRAW_DRAWER_PRIZE} 🪙 for drawing)")
    return True


def finish(room, text):
    game = state.drawings.get(room)
    if game is None:
        return
    word = game["word"]
    packet = round_packet(room, ended=True, word=word)
    del state.drawings[room]
    rooms.notify_room(room, text, kind="money" if "guessed it" in text else "event")
    send_round(room, packet)


def give_up(client):
    game = state.drawings.get(client.room)
    if game is None or game["drawer"] != client.key:
        client.say("🎨 You're not drawing right now.", "error")
        return
    finish(client.room, f"🏳️ {rooms.nick(client.key)} gave up. The word was {game['word'].upper()}.")


def end_due():
    """Called every few seconds: rounds whose time is up end, and the word is shown."""
    now = time.time()
    for room, game in list(state.drawings.items()):
        if now >= game["until"] or game["drawer"] not in state.online or state.online[game["drawer"]].room != room:
            finish(room, f"⏰ Time's up! The word was {game['word'].upper()}.")
