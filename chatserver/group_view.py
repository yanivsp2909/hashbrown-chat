"""
👥 What the website's Groups screen shows. These packets only SHOW things: every button on the screen sends an
existing /command, so the commands' own checks stay the only rules.

    browser -> server: {"type": "get_groups"}               the list (and keep it fresh while it's open)
                       {"type": "get_group", "group": key}  one group (and keep it fresh)
                       {"type": "groups_closed"}            the screen closed: no more updates
    server -> browser: {"type": "groups", "groups": [card, ...]}
                       {"type": "group_info", "group": details}

Privacy, all decided here:
- A private group you're not in: only its name, emoji and size (no topic, bank, upgrades, persona, members).
- "bank_details" (the bank's history, top donors, earnings, chart): only for members.
- "admin" (join requests, muted, banned): only for that group's owner and admins.
Old clients never send get_groups, so they never get any of this.
"""
import json
import time
import traceback

from chatserver import bank_log, config, rooms, state, textutil


def role_of(group, key):
    if key == group["owner"]:
        return "owner"
    if key in group["admins"]:
        return "admin"
    if key in group["members"]:
        return "member"
    if key in group["requests"]:
        return "requested"
    return "none"


def sees_inside(group, role):
    return not group["private"] or role in ("owner", "admin", "member")


def card(key, viewer):
    group = state.groups[key]
    role = role_of(group, viewer)
    shown = {"key": key, "name": group["name"], "emoji": group["emoji"], "private": group["private"],
             "members": len(group["members"]), "your_role": role}
    if sees_inside(group, role):
        shown.update({"online": sum(1 for m in group["members"] if m in state.online),"topic": group.get("topic", ""), "persona": group.get("personality") or "",
                      "bank": group["bank"], "upgrades": list(group["upgrades"])})
    return shown


def cards(viewer):
    """Your groups first (then by name), then the others."""
    keys = sorted(state.groups, key=lambda k: (role_of(state.groups[k], viewer) not in ("owner", "admin", "member"), k))
    return [card(key, viewer) for key in keys]


def upgrades(group):
    """Every upgrade, with its state: owned, can_buy (the bank has enough) or locked (and how much is missing)."""
    shown = []
    for name, (icon, price, does) in config.GROUP_UPGRADES.items():
        state_now = "owned" if name in group["upgrades"] else "can_buy" if group["bank"] >= price else "locked"
        row = {"name": name, "icon": icon, "price": price, "does": does, "state": state_now}
        if state_now == "locked":
            row["missing"] = price - group["bank"]
        shown.append(row)
    return shown


def member_role(group, login):
    return "owner" if login == group["owner"] else "admin" if login in group["admins"] else "member"


def war_status(key):
    for war in state.wars:
        if key in (war["a"], war["b"]):
            other = war["b"] if key == war["a"] else war["a"]
            return {"against": rooms.room_title(other), "us": war["points"].get(key, 0),
                    "them": war["points"].get(other, 0), "ends_in": max(0, int(war["until"] - time.time()))}
    invite = state.war_invites.get(key)
    if invite and invite[0] in state.groups:
        return {"invited_by": rooms.room_title(invite[0])}
    return None


def bank(key, group):
    online = [m for m in group["members"] if m in state.online]
    return {"balance": group["bank"], "per_minute": config.GROUP_INCOME if online else 0,
            "members_online": len(online), "income_upgrade": "income" in group["upgrades"],
            "history": bank_log.recent(key), "top_donors": bank_log.top_donors(key), "chart": bank_log.chart(key)}


def details(key, viewer):
    group = state.groups[key]
    shown = card(key, viewer)
    role = shown["your_role"]
    if not sees_inside(group, role):
        return shown
    shown["upgrades"] = upgrades(group)
    shown["admins"] = [rooms.nick(k) for k in [group["owner"]] + group["admins"] if k in state.accounts]
    shown["members_list"] = [{"name": rooms.nick(m), "role": member_role(group, m), "online": m in state.online}
                             for m in group["members"] if m in state.accounts]
    shown["war"] = war_status(key)
    if role in ("owner", "admin", "member"):
        shown["bank_details"] = bank(key, group)   # ("bank" is the balance, like on the card)
    if role in ("owner", "admin"):
        now = time.time()
        shown["admin"] = {
            "requests": [rooms.nick(k) for k in group["requests"] if k in state.accounts],
            "banned": [rooms.nick(k) for k in group["banned"] if k in state.accounts],
            "muted": [{"name": rooms.nick(who), "minutes": int((until - now) // 60) + 1}
                      for (room, who), until in state.mutes.items() if room == key and until > now and who in state.accounts],
        }
    return shown


# ---------------------------------------------------------------- the packets

def send_view(client, cache=None, force=True):
    """What this client's open screen shows: the list, or the list and one group. Packets that didn't change
    since the last time aren't sent again. cache: details already built in this round, by (group, role)."""
    if client.groups_view is None or client.key is None:
        return
    packets = [{"type": "groups", "groups": cards(client.key)}]
    key = client.groups_view
    if key in state.groups:
        role = role_of(state.groups[key], client.key)
        if cache is None or (key, role) not in cache:
            built = details(key, client.key)
            if cache is not None:
                cache[(key, role)] = built
        packets.append({"type": "group_info", "group": cache[(key, role)] if cache is not None else built})
    for packet in packets:
        text = json.dumps(packet, sort_keys=True)
        if force or client.groups_sent.get(packet["type"]) != text:
            client.groups_sent[packet["type"]] = text
            client.send(packet)


def handle(client, msg):
    kind = msg.get("type")
    if kind == "groups_closed":
        client.groups_view = None
        client.groups_sent = {}
        return
    if kind == "get_groups":
        client.groups_view = ""
    else:
        key = msg.get("group")
        if not isinstance(key, str) or key not in state.groups:
            client.say("👥 No group by that name.", "error")
            return
        client.groups_view = key
    send_view(client)


def mark_dirty():
    state.groups_dirty = True


def push_updates():
    """Called every second: if something changed, every open Groups screen gets fresh data."""
    if not state.groups_dirty:
        return
    state.groups_dirty = False
    cache = {}   # one group's details are built once per round for each role, however many people look
    for client in list(state.online.values()):
        try:
            send_view(client, cache, force=False)
        except Exception:   # one broken view mustn't stop everyone else's
            textutil.log("[SERVER] Error while refreshing a Groups screen:\n" + traceback.format_exc())
