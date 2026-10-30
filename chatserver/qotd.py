"""
💡 Answers to the question of the day: /answer posts one per person per day in the lobby, people vote with
reactions, and when the next question comes the answer with the most votes wins QOTD_PRIZE.
(The question itself is asked in hashbrown_extras.py.) Saved in chat_data.json under "qotd".
"""
import time

from chatserver import config, fund, history, rooms, state, storage, textutil


def empty():
    """No answers yet. "day" is the question's day, "answers" is [{login, id, text}] in the order they came."""
    return {"day": "", "answers": []}


def todays_question():
    """Today's question, or None if Hashbrown hasn't asked one yet."""
    if state.qotd and state.qotd[0] == textutil.today() and state.qotd[1]:
        return state.qotd[1]
    return None


def post_answer(client, text):
    """/answer text: post the card in the lobby. Returns an error message, or None when it was posted."""
    if todays_question() is None:
        return "❓ No question of the day yet. Hashbrown asks one in the lobby every day."
    if not text:
        return "💡 Use: /answer your answer"
    if state.qotd_answers["day"] != state.qotd[0]:
        state.qotd_answers = {**empty(), "day": state.qotd[0]}
    if any(a["login"] == client.key for a in state.qotd_answers["answers"]):
        return "💡 You already answered today's question. Vote for the others with reactions!"
    if state.mutes.get(("lobby", client.key), 0) > time.time():
        return "🔇 You're muted in the lobby."
    account = state.accounts[client.key]
    msg = rooms.chat_message(account["nick"], account["badge"],
                             f"💡 {account['nick']}'s answer: {text[:config.QOTD_ANSWER_MAX]}")
    history.add("lobby", msg)   # no author login: an answer can't be edited after people voted on it
    rooms.send_room("lobby", msg)
    answers = state.qotd_answers["answers"] + [{"login": client.key, "id": msg["id"], "text": msg["text"]}]
    state.qotd_answers = {**state.qotd_answers, "answers": answers}
    storage.save_data()   # on disk now: a crash mustn't lose an answer people vote on
    return None


def votes(answer):
    """How many OTHER people reacted to this answer (your own reactions don't count)."""
    voters = history.reactors([answer["id"]]).get(answer["id"], set())
    return len(voters - {answer["login"]})


def settle():
    """The next question is coming: the answer with the most votes (the earliest one on a tie) wins the
    prize and Hashbrown says so. No votes at all, no winner. Then the answers are cleared."""
    answers = [a for a in state.qotd_answers["answers"] if a["login"] in state.accounts and isinstance(a["id"], int)]
    state.qotd_answers = empty()
    scored = [(votes(a), a) for a in answers]
    best_votes, best = max(scored, key=lambda pair: pair[0], default=(0, None))   # max keeps the first on a tie
    if best is None or best_votes == 0:
        return
    account = state.accounts[best["login"]]
    fund.pay_prize(best["login"], config.QOTD_PRIZE)   # 🧾 from the public fund first
    text = best["text"].split(": ", 1)[-1]
    msg = rooms.chat_message("Hashbrown", "🥔",
                             f"🏆 Yesterday's best answer: {account['nick']} with \"{text}\" "
                             f"({best_votes} vote{'' if best_votes == 1 else 's'}). +{config.QOTD_PRIZE} 🪙!")
    history.add("lobby", msg)
    rooms.send_room("lobby", msg)
    storage.save_data()


def to_saved():
    """What goes into chat_data.json."""
    day, question = state.qotd if state.qotd else ("", None)
    return {"day": day, "question": question, "answers": state.qotd_answers["answers"],
            "answers_day": state.qotd_answers["day"]}


def load_saved(saved):
    """Back from chat_data.json (anything that doesn't look right is ignored)."""
    state.qotd, state.qotd_answers = None, empty()
    if not isinstance(saved, dict):
        return
    if isinstance(saved.get("day"), str) and isinstance(saved.get("question"), str):
        state.qotd = (saved["day"], saved["question"])
    answers = saved.get("answers")
    if isinstance(answers, list) and isinstance(saved.get("answers_day"), str):
        good = [a for a in answers if isinstance(a, dict) and isinstance(a.get("login"), str)
                and isinstance(a.get("id"), int) and isinstance(a.get("text"), str)]
        state.qotd_answers = {"day": saved["answers_day"], "answers": good}
