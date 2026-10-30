"""
🏠 Names, rooms and sending messages to people.
"""
import time
from datetime import datetime

from chatserver import config, state


# ---------------------------------------------------------------- small helpers

def valid_name(name):
    return (3 <= len(name) <= 16 and all(ch.isalnum() or ch == "_" for ch in name)
            and name.lower() not in config.RESERVED_NAMES)

def nick(key):
    return state.accounts[key]["nick"]

def shown(key):
    """Name with badge, like '👑 Yaniv'."""
    account = state.accounts[key]
    return f"{account['badge']} {account['nick']}" if account["badge"] else account["nick"]

def find_account(name):
    name = name.lower().lstrip("@")
    for key, account in state.accounts.items():
        if account["nick"].lower() == name:
            return key
    return None

def find_online(client, name):
    key = find_account(name) if name else None
    if key is None or key not in state.online:
        client.say(f"❓ {name or 'Who'} isn't online. See /users", "error")
        return None
    return key

def room_title(room):
    if room == "lobby":
        return "🏠 Lobby"
    group = state.groups[room]
    emoji = group["emoji"] + " " if group["emoji"] else ""
    return emoji + ("🔒" if group["private"] else "#") + group["name"]

def send_room(room, obj, exclude=None):
    for c in list(state.online.values()):
        if c.room == room and c is not exclude:
            c.send(obj)

def notify_room(room, text, exclude=None, kind="system"):
    send_room(room, {"type": "msg", "kind": kind, "text": text}, exclude)

def announce(text, kind="event", exclude=()):
    for key, c in list(state.online.items()):
        if key not in exclude:
            c.say(text, kind)

def tell(key, text, kind="system"):
    if key in state.online:
        state.online[key].say(text, kind)

def parse_amount(client, text):
    """Turn '50' or 'all' into a number of tokens the client actually has."""
    balance = state.accounts[client.key]["tokens"]
    text = text.strip().lower()
    if text == "all":
        amount = balance
    elif text.isdecimal() and len(text) < 10:
        amount = int(text)
    else:
        client.say("💰 The amount must be a number (or 'all').", "error")
        return None
    if amount <= 0:
        client.say("💰 The amount must be more than 0.", "error")
        return None
    if amount > balance:
        client.say(f"💸 You only have {balance} 🪙.", "error")
        return None
    return amount

def move_to_room(client, room):
    old = client.room
    client.room = room
    if old != room:  # groups get enter/leave notices; the lobby would be too noisy
        if old != "lobby":
            notify_room(old, f"🚪 {shown(client.key)} left the room")
        if room != "lobby":
            notify_room(room, f"➡️ {shown(client.key)} entered", exclude=client)
    client.send({"type": "history", "room": room_title(room), "messages": list(state.history[room])})

def spam_ok(client):
    now = time.time()
    while client.recent and now - client.recent[0] > config.SPAM_WINDOW:
        client.recent.popleft()
    if len(client.recent) >= config.SPAM_LIMIT:
        client.say("🐢 Slow down! You're sending too fast.", "error")
        return False
    client.recent.append(now)
    return True

# ----- 👥 Groups

def current_group(client):
    if client.room == "lobby":
        client.say("🏠 You're in the lobby. /join a group first.", "error")
        return None, None
    return client.room, state.groups[client.room]

def is_admin(group, key):
    return key == group["owner"] or key in group["admins"]

def chat_message(name, badge, text, action=False):
    return {"type": "chat", "time": datetime.now().strftime("%H:%M"), "name": name,
            "badge": badge, "text": text, "action": action}
