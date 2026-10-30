"""
🥔 Hashbrown extras that the SERVER starts, when nobody asked: the game commentator and the question of the day.
The server pays for these; they count toward the server-wide daily cap (HASHBROWN_DAILY_CAP), and if the AI
call fails nothing happens (there's nobody to refund). The commands people type are in cmd_ask.py.
"""
import re
import threading

from chatserver import config, hashbrown_ai, history, matches, rooms, state, storage, textutil
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


def give_back_server_question(day):
    """A server question failed: it shouldn't use up the day's cap."""
    if state.hashbrown_all_today[0] == day:
        state.hashbrown_all_today = (day, max(0, state.hashbrown_all_today[1] - 1))


def ask_in_background(task, deliver, on_fail=None):
    """Ask Hashbrown in its own thread; deliver(answer) then runs while holding the lock."""
    messages = [{"role": "system", "content": config.HASHBROWN_PROMPT}, {"role": "user", "content": task}]
    day = textutil.today()

    def work():
        try:
            answer = hashbrown_ai.call_hashbrown(messages)
        except Exception as e:  # the chat must survive anything the network does
            textutil.log(f"[HASHBROWN] Error (server question): {hashbrown_ai.describe_error(e)}")
            with state.lock:
                give_back_server_question(day)
                if on_fail:
                    on_fail()
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

    def failed():
        if state.commentator_today[0] == day:
            state.commentator_today = (day, max(0, state.commentator_today[1] - 1))
    ask_in_background(task, deliver, failed)


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



# ---------------------------------------------------------------- 🧠 trivia

TRIVIA_TASK = ("Write one fun trivia question for friends in a group chat, with a short answer (one or two words, "
               "or a number). Reply in exactly this format and nothing else:\nQUESTION: ...\nANSWER: ...")
TRIVIA_REPLY = re.compile(r"QUESTION:\s*(?P<question>.+?)\s*\n\s*ANSWER:\s*(?P<answer>[^\n]+)", re.IGNORECASE | re.DOTALL)


def normalize(text):
    """'The PARIS!' and 'paris' are the same answer: no case, no 'the/a/an', no punctuation or spaces."""
    text = re.sub(r"^(the|a|an)\s+", "", text.strip().lower())
    return re.sub(r"[\W_]+", "", text)


def start_trivia(client):
    """/trivia: the asker pays like /ask; Hashbrown writes a question and the room races to answer it."""
    room, account = client.room, state.accounts[client.key]
    if state.hashbrown is None:
        client.say("🥔💤 Hashbrown is asleep (the server owner hasn't set it up yet).", "error")
        return
    if room in state.trivia:
        client.say("🧠 There's already a trivia question here. Answer it first!", "error")
        return
    if account["tokens"] < config.HASHBROWN_COST:
        client.say(f"💸 Trivia costs {config.HASHBROWN_COST} 🪙.", "error")
        return
    if not take_server_question():
        client.say("🥔😴 Hashbrown has answered enough for today. Try tomorrow!", "error")
        return
    account["tokens"] -= config.HASHBROWN_COST
    state.trivia[room] = {"pending": True}
    asker = client.key

    def refund(why):
        state.trivia.pop(room, None)
        if asker in state.accounts:
            state.accounts[asker]["tokens"] += config.HASHBROWN_COST
            storage.save_data()
        rooms.tell(asker, why, "error")

    def deliver(reply):
        found = TRIVIA_REPLY.search(reply)
        if not found or not normalize(found["answer"]):   # regex, no second AI call: the format is fixed
            refund("🧠 Hashbrown's question came out wrong. Your tokens were refunded.")
            return
        trivia = {"answer": normalize(found["answer"]), "shown": found["answer"].strip()}
        state.trivia[room] = trivia
        msg = rooms.chat_message("Hashbrown", "🥔", f"🧠 Trivia: {found['question'].strip()} "
                                                    f"(first right answer wins {config.TRIVIA_REWARD} 🪙)")
        history.add(room, msg)
        rooms.send_room(room, msg)
        threading.Timer(config.TRIVIA_SECONDS, time_up_later, args=(room, trivia)).start()

    ask_in_background(TRIVIA_TASK, deliver,
                      lambda: refund("🧠 Hashbrown couldn't think of a question. Your tokens were refunded."))


def time_up_later(room, trivia):
    with state.lock:
        trivia_time_up(room, trivia)


def trivia_time_up(room, trivia):
    if state.trivia.get(room) is trivia:
        del state.trivia[room]
        rooms.notify_room(room, f"⏰ Trivia over! The answer was {trivia['shown']}.", kind="event")


def check_trivia(client, text):
    """Called for every chat line: is it the right answer to this room's trivia?"""
    trivia = state.trivia.get(client.room)
    if not trivia or "answer" not in trivia or normalize(text) != trivia["answer"]:
        return
    del state.trivia[client.room]
    state.accounts[client.key]["tokens"] += config.TRIVIA_REWARD
    storage.save_data()
    rooms.notify_room(client.room, f"🧠 {rooms.shown(client.key)} got it: {trivia['shown']}! "
                                   f"+{config.TRIVIA_REWARD} 🪙", kind="event")
