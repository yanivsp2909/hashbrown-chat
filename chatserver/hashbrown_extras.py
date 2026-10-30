"""
🥔 Hashbrown extras that the SERVER starts, when nobody asked: the game commentator and the question of the day.
The server pays for these; they count toward the server-wide daily cap (HASHBROWN_DAILY_CAP), and if the AI
call fails nothing happens (there's nobody to refund). The commands people type are in cmd_ask.py.
"""
import threading

from chatserver import config, hashbrown_ai, history, matches, rooms, state, textutil
from chatserver.hashbrown_text import israel_now


def take_server_question():
    """True (and counted) if Hashbrown is awake and today's server-wide cap isn't used up."""
    if state.hashbrown is None:
        return False
    day, asked = state.hashbrown_all_today
    if day != textutil.today():
        day, asked = textutil.today(), 0
    if asked >= config.HASHBROWN_DAILY_CAP:
        return False
    state.hashbrown_all_today = (day, asked + 1)
    return True


def ask_in_background(task, deliver):
    """Ask Hashbrown in its own thread; deliver(answer) then runs while holding the lock."""
    messages = [{"role": "system", "content": config.HASHBROWN_PROMPT}, {"role": "user", "content": task}]

    def work():
        try:
            answer = hashbrown_ai.call_hashbrown(messages)
        except Exception as e:  # the chat must survive anything the network does
            textutil.log(f"[HASHBROWN] Error (server question): {hashbrown_ai.describe_error(e)}")
            return
        with state.lock:
            deliver(answer)
    threading.Thread(target=work, daemon=True).start()


# ---------------------------------------------------------------- 🎙️ the game commentator

def commentate(match, winner):
    """Called after every finished match (matches.finish_hooks): one funny line for both players."""
    if not config.COMMENTATOR or state.hashbrown is None:
        return
    day, done = state.commentator_today
    if day != textutil.today():
        day, done = textutil.today(), 0
    if done >= config.COMMENTATOR_PER_DAY or not take_server_question():
        return
    state.commentator_today = (day, done + 1)
    p1, p2 = match.players
    result = "It ended in a draw" if winner in ("draw", None) else f"{rooms.nick(winner)} won"
    task = (f"{rooms.nick(p1)} and {rooms.nick(p2)} just finished a game of {match.game.title}. {result}. "
            f"The final board:\n{match.game.render(p1)}\n\n"
            "Say ONE short, funny sports-commentator line about it.")

    def deliver(answer):
        for p in match.players:
            rooms.tell(p, f"🎙️ Hashbrown: {answer}", "game")
    ask_in_background(task, deliver)


matches.finish_hooks.append(commentate)


# ---------------------------------------------------------------- ❓ the question of the day

def question_of_the_day_tick():
    """Once a day (after QOTD_HOUR in Israel), with at least two people online, Hashbrown asks the lobby
    a fun question. Called every minute by background.qotd_loop."""
    with state.lock:
        today = textutil.today()
        if state.qotd and state.qotd[0] == today:
            return
        if israel_now().hour < config.QOTD_HOUR or len(state.online) < 2 or not take_server_question():
            return
        state.qotd = (today, None)   # asked: don't ask again today, even if the call fails

    def deliver(answer):
        state.qotd = (today, answer)
        msg = rooms.chat_message("Hashbrown", "🥔", f"❓ Question of the day: {answer}")
        history.add("lobby", msg)
        rooms.send_room("lobby", msg)
    ask_in_background("Ask the friends in the group chat one fun question of the day (one sentence, "
                      "nothing too personal). Only the question.", deliver)
