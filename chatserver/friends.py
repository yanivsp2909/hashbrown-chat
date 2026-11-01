"""
🤝 Friends.

    account["friends"]          [logins]   always both ways: if Ben is Adi's friend, Adi is Ben's (saved)
    account["friend_requests"]  [logins]   who asked to be your friend and is waiting for your answer (saved)
    state.friend_noes           {(asker, asked): time}   a "no" (or a request taken back): no asking again right away

Apps that put "friends" in their login features get {"type": "friends", "friends": [...], "requests": [...],
"sent": [...], "groups": [...]} whenever it changes (push_updates runs every second, and only sends a change).
"""
import time
import traceback

from chatserver import config, profiles, rooms, state, textutil

ACCOUNT_FIELDS = ("friends", "friend_requests")


def defaults():
    return {"friends": [], "friend_requests": []}


def are_friends(a, b):
    return b in state.accounts[a]["friends"]


def asked(asker, target):
    """Is a request from `asker` waiting for `target`?"""
    return asker in state.accounts[target]["friend_requests"]


# ---------------------------------------------------------------- asking, answering, removing

def refusal(client, target):
    """Why `client` can't ask `target` to be friends, or None."""
    me, them = state.accounts[client.key], state.accounts[target]
    if target == client.key:
        return "🙃 You can't add yourself."
    if are_friends(client.key, target):
        return f"🤝 You and {rooms.nick(target)} are already friends."
    if asked(client.key, target):
        return f"⏳ Already asked. Waiting for {rooms.nick(target)}."
    said_no = state.friend_noes.get((client.key, target), 0)
    if time.time() - said_no < config.FRIEND_RETRY_SECONDS:
        return f"⏳ {rooms.nick(target)} said no a moment ago. Try again later."
    if len(me["friends"]) >= config.FRIENDS_MAX:
        return f"🤝 You already have {config.FRIENDS_MAX} friends. Remove someone first."
    if len(them["friends"]) >= config.FRIENDS_MAX:
        return f"🤝 {rooms.nick(target)} already has {config.FRIENDS_MAX} friends."
    if len(sent_by(client.key)) >= config.FRIEND_SENT_MAX:
        return f"🤝 You have {config.FRIEND_SENT_MAX} friend requests waiting for answers. Wait, or take some back."
    if len(them["friend_requests"]) >= config.FRIEND_REQUESTS_MAX:
        return f"🤝 {rooms.nick(target)} has too many friend requests waiting. Try again later."
    if them["privacy"]["dms"] == "friends":   # friends-only people can still be asked (or nobody could add them)
        return None
    return profiles.dm_refusal(client.key, target, "friend requests")   # 🔕 "who can message me"


def ask(client, target):
    """/friend add name. If they already asked you, this is a yes."""
    if asked(target, client.key):
        return accept(client, target)
    why_not = refusal(client, target)
    if why_not:
        client.say(why_not, "error")
        return False
    state.accounts[target]["friend_requests"].append(client.key)
    name = rooms.nick(client.key)
    rooms.tell(target, f"🤝 {rooms.shown(client.key)} wants to be friends!  /friend accept {name}  or  "
                       f"/friend decline {name}", "event")
    client.say(f"🤝 Asked {rooms.shown(target)} to be friends.")
    return True


def accept(client, asker):
    requests = state.accounts[client.key]["friend_requests"]
    if asker not in requests:
        client.say(f"❓ {rooms.nick(asker)} didn't ask to be your friend.", "error")
        return False
    if len(state.accounts[client.key]["friends"]) >= config.FRIENDS_MAX:
        client.say(f"🤝 You already have {config.FRIENDS_MAX} friends. Remove someone first.", "error")
        return False
    if len(state.accounts[asker]["friends"]) >= config.FRIENDS_MAX:
        client.say(f"🤝 {rooms.nick(asker)} already has {config.FRIENDS_MAX} friends.", "error")
        return False
    requests.remove(asker)
    for a, b in ((client.key, asker), (asker, client.key)):
        if b not in state.accounts[a]["friends"]:
            state.accounts[a]["friends"].append(b)
        if b in state.accounts[a]["friend_requests"]:   # (they had asked each other)
            state.accounts[a]["friend_requests"].remove(b)
    client.say(f"🤝 You and {rooms.shown(asker)} are friends now!", "event")
    rooms.tell(asker, f"🤝 You and {rooms.shown(client.key)} are friends now!", "event")
    return True


def decline(client, asker):
    requests = state.accounts[client.key]["friend_requests"]
    if asker not in requests:
        client.say(f"❓ {rooms.nick(asker)} didn't ask to be your friend.", "error")
        return False
    requests.remove(asker)
    state.friend_noes[(asker, client.key)] = time.time()
    client.say(f"👎 You said no to {rooms.shown(asker)}.")
    rooms.tell(asker, f"🤝 {rooms.shown(client.key)} said no to your friend request.")
    return True


def remove(client, target):
    """/friend remove name: no longer friends (both ways), or a request you sent is taken back."""
    if are_friends(client.key, target):
        state.accounts[client.key]["friends"].remove(target)
        if client.key in state.accounts[target]["friends"]:   # (always both ways, unless the data was bad)
            state.accounts[target]["friends"].remove(client.key)
        client.say(f"🤝 Removed {rooms.shown(target)} from your friends.")
        return True
    if asked(client.key, target):
        state.accounts[target]["friend_requests"].remove(client.key)
        state.friend_noes[(client.key, target)] = time.time()   # (so take back + ask again can't be used to spam)
        client.say(f"🤝 Took back your friend request to {rooms.shown(target)}.")
        return True
    client.say(f"❓ {rooms.nick(target)} isn't your friend.", "error")
    return False


# ---------------------------------------------------------------- what your friends are doing

def where(viewer, friend):
    """The room a friend is in, as the viewer may see it (a private group's name only for its members)."""
    room = state.online[friend].room
    group = state.groups.get(room)
    if room != "lobby" and group is None:   # (a group that just went away)
        return rooms.room_title("lobby")
    if group is not None and group["private"] and viewer not in group["members"]:
        return "🔒 a private group"
    return rooms.room_title(room)


def row(viewer, friend):
    online = friend in state.online
    return {"name": rooms.nick(friend), "online": online, "status": state.accounts[friend]["status"],
            "room": where(viewer, friend) if online else "", "playing": online and friend in state.matches}


def sent_map():
    """asker -> [who they asked], for everyone at once (one pass over the accounts)."""
    sent = {}
    for target, account in state.accounts.items():
        for asker in account["friend_requests"]:
            sent.setdefault(asker, []).append(target)
    return sent


def sent_by(login):
    return sent_map().get(login, [])


def admin_groups():
    """login -> [{key, name}] of the groups they're an admin of, A to Z (one pass over the groups)."""
    mine = {}
    for key, g in sorted(state.groups.items()):
        for admin in [g["owner"]] + g["admins"]:
            mine.setdefault(admin, []).append({"key": key, "name": g["name"]})
    return mine


def packet(login, sent=None, groups=None):
    """The website's friends list: online friends first (then A to Z), the requests, and your admin groups
    (for the "invite to my group" button). sent / groups: sent_map() / admin_groups(), if already made."""
    sent = sent_map() if sent is None else sent
    groups = admin_groups() if groups is None else groups
    mine = sorted(state.accounts[login]["friends"], key=lambda k: (k not in state.online, rooms.nick(k).lower()))
    return {"type": "friends", "friends": [row(login, k) for k in mine if k in state.accounts],
            "requests": [rooms.nick(k) for k in state.accounts[login]["friend_requests"] if k in state.accounts],
            "sent": [rooms.nick(k) for k in sent.get(login, [])], "groups": groups.get(login, [])}


def push_updates():
    """Every second (background.py): apps that show a friends list get it again if anything in it changed.
    One person's broken list never stops the others'."""
    watchers = [(login, c) for login, c in list(state.online.items()) if "friends" in c.features and c.key == login]
    if not watchers:
        return
    sent, groups = sent_map(), admin_groups()
    for login, client in watchers:
        try:
            fresh = packet(login, sent, groups)
        except Exception:   # a bug for one person: log it, and the others still get theirs
            textutil.log("[SERVER] Couldn't build a friends list:\n" + traceback.format_exc())
            continue
        if fresh != client.friends_sent:
            client.friends_sent = fresh
            client.send(fresh)


def announce_online(login):
    """👥 A small notice for your friends who are online (at a password login, not a quiet reconnect)."""
    for friend in state.accounts[login]["friends"]:
        if friend in state.online:
            state.online[friend].say(f"👥 Your friend {rooms.shown(login)} is online.")


def lines(login):
    """/friends as text."""
    account = state.accounts[login]
    mine = sorted(account["friends"], key=lambda k: (k not in state.online, rooms.nick(k).lower()))
    if not mine and not account["friend_requests"]:
        return "🤝 No friends yet. Ask someone with /friend add name"
    out = [f"🤝 Your friends ({len(mine)}):"]
    for friend in mine:
        info = row(login, friend)
        doing = f"{info['room']}{'  🎮 playing' if info['playing'] else ''}" if info["online"] else "offline"
        out.append(f"  {'🟢' if info['online'] else '⚫'} {rooms.shown(friend)}  {doing}")
    for asker in account["friend_requests"]:
        name = rooms.nick(asker)
        out.append(f"  📨 {name} wants to be friends:  /friend accept {name}  or  /friend decline {name}")
    return "\n".join(out)


# ---------------------------------------------------------------- loading

def clean_saved(accounts):
    """After chat_data.json is read: only real accounts, no duplicates, nobody their own friend, both ways."""
    for login, account in accounts.items():
        for field in ACCOUNT_FIELDS:
            value = account.get(field)
            names = value if isinstance(value, list) else []
            kept = []
            for name in names:
                if isinstance(name, str) and name in accounts and name != login and name not in kept:
                    kept.append(name)
            account[field] = kept[:config.FRIENDS_MAX if field == "friends" else config.FRIEND_REQUESTS_MAX]
    for login, account in accounts.items():   # a friendship is always both ways
        for friend in account["friends"]:
            if login not in accounts[friend]["friends"]:
                accounts[friend]["friends"].append(login)
    for account in accounts.values():          # and a friend isn't also waiting to be one
        account["friend_requests"] = [k for k in account["friend_requests"] if k not in account["friends"]]
