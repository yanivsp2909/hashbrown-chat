"""
⏰ /remind 10m text: Hashbrown's server reminds you privately later.
At most REMIND_MAX waiting per person, up to REMIND_MAX_HOURS ahead. Saved in chat_data.json ("reminders"),
so a restart doesn't lose them. If you're away when one is due, you get it when you log in.
"""
import re
import time
from datetime import datetime

from chatserver import config, rooms, state, storage

DURATION = re.compile(r"(?:(\d{1,3})h)?(?:(\d{1,4})m)?(?:(\d{1,5})s)?", re.IGNORECASE)


def parse_duration(text):
    """"10m" / "2h" / "1h30m" / "90s" -> seconds, or None (nothing, zero, or more than REMIND_MAX_HOURS)."""
    match = DURATION.fullmatch(text.strip())
    if not text.strip() or match is None:
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    total = hours * 3600 + minutes * 60 + seconds
    return total if 0 < total <= config.REMIND_MAX_HOURS * 3600 else None


def how_long(seconds):
    """5400 -> "1 h 30 min", 90 -> "1 min" (rounded up to whole minutes)."""
    minutes = -(-seconds // 60)
    hours, minutes = divmod(minutes, 60)
    return " ".join(part for part in (f"{hours} h" if hours else "", f"{minutes} min" if minutes else "") if part)


def add(client, args):
    """Returns an error message, or None when the reminder was saved."""
    when, _, text = args.strip().partition(" ")
    seconds = parse_duration(when)
    text = text.strip()[:config.REMIND_TEXT_MAX]
    if seconds is None or not text:
        return f"⏰ Use: /remind 10m text  (like 30m, 2h or 1h30m; up to {config.REMIND_MAX_HOURS}h)"
    if sum(1 for r in state.reminders if r["login"] == client.key) >= config.REMIND_MAX:
        return f"⏰ You can have at most {config.REMIND_MAX} reminders waiting."
    state.reminders = state.reminders + [{"login": client.key, "due": time.time() + seconds, "text": text}]
    storage.save_data()
    client.say(f"⏰ OK! I'll remind you in {how_long(seconds)}.")
    return None


def listing(client):
    mine = sorted((r for r in state.reminders if r["login"] == client.key), key=lambda r: r["due"])
    if not mine:
        return "⏰ No reminders waiting. Set one with /remind 10m text"
    rows = [f"  {datetime.fromtimestamp(r['due']).strftime('%H:%M')}  {r['text']}" for r in mine]
    return "⏰ Your reminders:\n" + "\n".join(rows)


def remind(key, reminder, late=False):
    when = f" (it was due at {datetime.fromtimestamp(reminder['due']).strftime('%H:%M')})" if late else ""
    rooms.tell(key, f"⏰ Reminder: {reminder['text']}{when}", "event")


def deliver_due(now=None):
    """Called every few seconds: due reminders go to whoever is online (the others wait for their login)."""
    now = time.time() if now is None else now
    due = [r for r in state.reminders if r["due"] <= now and r["login"] in state.online]
    if due:
        state.reminders = [r for r in state.reminders if r not in due]
        for reminder in due:
            remind(reminder["login"], reminder)
        storage.save_data()


def deliver_at_login(key):
    """Reminders that came due while you were away."""
    now = time.time()
    due = [r for r in state.reminders if r["login"] == key and r["due"] <= now]
    if due:
        state.reminders = [r for r in state.reminders if r not in due]
        for reminder in due:
            remind(key, reminder, late=True)
        storage.save_data()


def load_saved(saved):
    """From chat_data.json; anything that doesn't look right is dropped."""
    good = []
    for r in saved if isinstance(saved, list) else []:
        if (isinstance(r, dict) and isinstance(r.get("login"), str) and isinstance(r.get("text"), str)
                and isinstance(r.get("due"), (int, float)) and not isinstance(r.get("due"), bool)):
            good.append({"login": r["login"], "due": r["due"], "text": r["text"][:config.REMIND_TEXT_MAX]})
    state.reminders = good
