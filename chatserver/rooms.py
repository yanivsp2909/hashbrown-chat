"""
🏠 Names, rooms and sending messages to people.
"""
import re
import time
from datetime import datetime

from chatserver import config, history, resume, state


# ---------------------------------------------------------------- small helpers

ENGLISH = re.compile(r"[A-Za-z0-9_]+")
HEBREW = re.compile(r"[\u05d0-\u05ea0-9_]+")   # the 27 Hebrew letters (with the final forms), no vowel marks
NAME_RULE = "3-16 English or Hebrew letters, digits or _ (one alphabet per name)"


def valid_name(name):
    """🔤 For new names only (old accounts keep theirs): English OR Hebrew letters, digits 0-9 and _, so a name
    can't hide a look-alike letter from another alphabet (a Cyrillic "А" in "Аdi")."""
    return (3 <= len(name) <= 16 and bool(ENGLISH.fullmatch(name) or HEBREW.fullmatch(name))
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


def is_member(key, room):
    """Everyone is in the lobby; a group's rooms belong to its members."""
    return room == "lobby" or (room in state.groups and key in state.groups[room]["members"])


def send_room(room, obj, exclude=None):
    """Send to everyone in the room. Clients that said "rooms" at login (the chat switcher) also get the
    chat of their OTHER rooms, and every packet tells them which room it's from with "room"."""
    tagged = {**obj, "room": room}
    for c in list(state.online.values()):
        if c is not exclude and gets_it(c, room, obj):
            c.send(tagged if "rooms" in c.features else obj)
    resume.record_for_away(room, obj, is_member)   # 🔁 kept for whoever dropped a moment ago


def gets_it(client, room, obj):
    """Everyone in the room; and chat switcher clients also get the chat of their other rooms."""
    if client.room == room:
        return True
    return "rooms" in client.features and obj.get("type") == "chat" and is_member(client.key, room)


def send_room_list(key):
    """💬 The chat switcher's list: the lobby and your groups, and where you are now."""
    client = state.online.get(key)
    if client is None or "rooms" not in client.features:
        return
    mine = ["lobby"] + [k for k, g in state.groups.items() if key in g["members"]]
    client.send({"type": "rooms", "current": client.room,
                 "rooms": [{"key": k, "name": "Lobby" if k == "lobby" else state.groups[k]["name"],
                            "title": room_title(k)} for k in mine]})


def lab_packet():
    """🧪 {"type": "lab", "lag_ms", "loss_percent"}: the website shows a banner while the network lab is on."""
    return {"type": "lab", "lag_ms": state.lab_lag_ms, "loss_percent": state.lab_loss_percent}


def tell_everyone_about_the_lab():
    """The host changed the lab in the server window: everyone's banner changes (or goes away)."""
    for c in list(state.online.values()):
        c.send(lab_packet())


def notify_room(room, text, exclude=None, kind="system", **extra):
    send_room(room, {"type": "msg", "kind": kind, "text": text, **extra}, exclude)


def announce(text, kind="event", exclude=()):
    for key, c in list(state.online.items()):
        if key not in exclude:
            c.say(text, kind)
    for key in resume.away_keys():
        if key not in exclude:
            resume.record_to_away(key, {"type": "msg", "kind": kind, "text": text})


def tell(key, text, kind="system", **extra):
    if key in state.online:
        state.online[key].say(text, kind, **extra)
    else:
        resume.record_to_away(key, {"type": "msg", "kind": kind, "text": text, **extra})


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


def send_history(client, room):
    """The room's last messages. "room" is its title (to show); "key" says which room it is, so the website
    can keep one message list per room."""
    client.send({"type": "history", "room": room_title(room), "key": room, "messages": history.recent(room)})


def topic_of(room):
    """📌 The room's pinned topic ("" = none)."""
    return state.lobby_topic if room == "lobby" else state.groups.get(room, {}).get("topic", "")


def topic_packet(room):
    """{"type": "topic"}: the website shows it at the top of the chat ("" = take it away)."""
    return {"type": "topic", "room": room, "text": topic_of(room)}


def end_typing(client):
    """⌨️ They switched rooms or left while typing: the room stops showing "is typing…" right away."""
    if not client.is_typing:
        return
    client.is_typing, client.last_typing = False, 0.0
    note = {"type": "typing_stop", "name": nick(client.key)}
    for other in list(state.online.values()):
        if other is not client and other.room == client.room and "typing" in other.features:
            other.send({**note, "room": client.room} if "rooms" in other.features else note)


def move_to_room(client, room):
    end_typing(client)
    old = client.room
    client.room = room
    if old != room:  # groups get enter/leave notices; the lobby would be too noisy
        if old != "lobby":
            notify_room(old, f"🚪 {shown(client.key)} left the room")
        if room != "lobby":
            notify_room(room, f"➡️ {shown(client.key)} entered", exclude=client)
    send_history(client, room)
    send_room_list(client.key)
    client.send(topic_packet(room))   # 📌 (an empty one clears the last room's)
    from chatserver import drawing   # (drawing uses rooms: importing it at the top would loop)
    drawing.on_enter(client)          # 🎨 a round going on here: the drawing so far
    if topic_of(room):
        client.say(f"📌 Topic: {topic_of(room)}")


def spam_ok(client):
    now = time.time()
    while client.recent and now - client.recent[0] > config.SPAM_WINDOW:
        client.recent.popleft()
    if len(client.recent) >= config.SPAM_LIMIT:
        client.say("🐢 Slow down! You're sending too fast.", "error")
        return False
    client.recent.append(now)
    return True


# ----- 👥 Group helpers and chat lines

def current_group(client):
    if client.room == "lobby":
        client.say("🏠 You're in the lobby. /join a group first.", "error")
        return None, None
    return client.room, state.groups[client.room]


def is_admin(group, key):
    return key == group["owner"] or key in group["admins"]


def chat_message(name, badge, text, action=False):
    """A chat packet. history.add() gives it its "id" once it is saved."""
    return {"type": "chat", "time": datetime.now().strftime("%H:%M"), "name": name,
            "badge": badge, "text": text, "action": action}
