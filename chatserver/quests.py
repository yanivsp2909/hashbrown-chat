"""
🎯 Daily quests: three small tasks a day, the same three for everyone (picked from QUESTS by the date), each
paying tokens once. Progress lives in the account: "quests": {"day", "progress": {quest: count}, "done": [...]}.
"""
import random

from chatserver import achievements, matches, rooms, state, textutil

# id: (what to do, how many times, reward)
QUESTS = {
    "win": ("Win a game", 1, 40),
    "play": ("Play 2 games", 2, 25),
    "chat": ("Send 10 messages", 10, 20),
    "wordle": ("Finish a Wordle", 1, 30),
    "dm": ("Send someone a private message", 1, 15),
}
PER_DAY = 3


def todays(day=None):
    """The three quest ids for this day (the date is the seed, so everyone gets the same ones)."""
    day = day or textutil.today()
    return random.Random(day).sample(sorted(QUESTS), PER_DAY)


def progress_of(key):
    """This account's progress for today (yesterday's starts again from zero)."""
    account = state.accounts[key]
    saved = account.get("quests")
    if not isinstance(saved, dict) or saved.get("day") != textutil.today():
        saved = {"day": textutil.today(), "progress": {}, "done": []}
        account["quests"] = saved
    return saved


def bump(key, quest, amount=1):
    """Something counted toward a quest. When it's reached: pay once and say so."""
    if key not in state.accounts or quest not in todays():
        return
    saved = progress_of(key)
    if quest in saved["done"]:
        return
    what, goal, reward = QUESTS[quest]
    count = min(goal, saved["progress"].get(quest, 0) + amount)
    saved["progress"] = {**saved["progress"], quest: count}
    if count >= goal:
        saved["done"] = saved["done"] + [quest]
        state.accounts[key]["tokens"] += reward
        rooms.tell(key, f"🎯 Quest done: {what}! +{reward} 🪙", "money")
        achievements.check_rich(key)


def listing(key):
    saved = progress_of(key)
    rows = []
    for quest in todays():
        what, goal, reward = QUESTS[quest]
        mark = "✅" if quest in saved["done"] else "⬜"
        rows.append(f"  {mark} {what}  {saved['progress'].get(quest, 0)}/{goal}  +{reward} 🪙")
    return "🎯 Today's quests (new ones every day):\n" + "\n".join(rows)


def after_match(match, winner):
    """matches.finish_hooks: a really played game counts for both, a win for the winner."""
    if not matches.was_played(match):
        return
    for player in match.players:
        bump(player, "play")
    if winner in match.players:
        bump(winner, "win")


matches.finish_hooks.append(after_match)   # 🎯 played / won games count toward the daily quests
