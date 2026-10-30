"""
💾 Saving and loading chat_data.json (accounts and groups; the chat history lives in history.db, see history.py).
"""
import json
import os
import time

from chatserver import config, qotd, reminders, state, textutil


# ---------------------------------------------------------------- saving / loading

def load_data():
    """Read chat_data.json. Returns False if the file is damaged: then the server must NOT
    start, or the next save would overwrite everyone's accounts."""
    if os.path.exists(config.DATA_FILE):
        try:
            with open(config.DATA_FILE, encoding="utf-8") as f:
                data = json.load(f)
            state.accounts, state.groups = dict(data.get("accounts", {})), dict(data.get("groups", {}))
            pot = data.get("jackpot", 0)   # added later: older files don't have it
            state.jackpot = pot if isinstance(pot, int) and pot >= 0 else 0
            qotd.load_saved(data.get("qotd"))   # ❓💡 added later too
            reminders.load_saved(data.get("reminders", []))   # ⏰ and this
            topic = data.get("lobby_topic", "")   # 📌 and this
            state.lobby_topic = topic[:config.TOPIC_MAX] if isinstance(topic, str) else ""
            tips = data.get("hashbrown_tokens", 0)   # 🥔 and this
            state.hashbrown_tokens = tips if isinstance(tips, int) and not isinstance(tips, bool) and tips >= 0 else 0
        except (OSError, ValueError, AttributeError, TypeError) as e:
            textutil.log(f"[SERVER] ❌ Can't read {config.DATA_FILE} ({type(e).__name__}). It may be damaged. "
                         f"The server did not start, so nothing was overwritten. Fix the file or move it away.")
            return False
    # Files saved by an older version are missing the newer fields: fill them in
    for account in state.accounts.values():
        account.setdefault("created", 0)   # made before we kept the time: certainly older than a day
        for field, default in new_account("", "", "").items():
            account.setdefault(field, default)
    for key, group in state.groups.items():
        for field, default in new_group(key, "", False).items():
            group.setdefault(field, default)
    textutil.log(f"[SERVER] Loaded {len(state.accounts)} accounts and {len(state.groups)} groups")
    return True


def save_data():
    """Write everything to chat_data.json. Returns False (and logs why) if it couldn't:
    the data stays in memory and the next save tries again."""
    with state.lock:
        tmp = config.DATA_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"accounts": state.accounts, "groups": state.groups, "jackpot": state.jackpot,
                           "qotd": qotd.to_saved(), "reminders": state.reminders,
                           "lobby_topic": state.lobby_topic, "hashbrown_tokens": state.hashbrown_tokens},
                          f, ensure_ascii=False, indent=1)
                f.flush()
                os.fsync(f.fileno())  # really on the disk, even if the power goes out right after
            for attempt in range(3):
                try:
                    os.replace(tmp, config.DATA_FILE)  # swap in one step, so a crash never leaves a half file
                    break
                except PermissionError:  # Windows: an antivirus can hold the file for a moment
                    if attempt == 2:
                        raise
                    time.sleep(0.1)
            return True
        except (OSError, ValueError) as e:
            textutil.log(f"[SERVER] ⚠️ Couldn't save {config.DATA_FILE}: {e}")
            return False


# ---------------------------------------------------------------- new accounts and groups

def new_account(username, salt, digest):
    return {"login": username, "nick": username, "salt": salt, "hash": digest,
            "tokens": config.START_TOKENS, "badge": "", "badges": [], "wins": 0, "losses": 0,
            "draws": 0, "last_daily": 0, "streak": 0, "messages": 0, "achievements": [],
            "win_day": "", "rewarded_wins": 0, "solo_day": "", "solo_rewarded": 0,
            "admin": False, "joined": textutil.today(), "elo": config.START_ELO,
            "inbox": [],   # 📬 private messages that came while they were offline
            "created": time.time(),   # 🎁 when it was made: new accounts can't /give yet
            "given": ["", 0]}         # 🎁 [day, tokens given with /give that day]


def new_group(name, owner, private):
    return {"name": name, "owner": owner, "admins": [], "members": [owner] if owner else [],
            "banned": [], "requests": [], "private": private, "bank": 0, "upgrades": [], "emoji": "",
            "topic": ""}   # 📌 /pin
