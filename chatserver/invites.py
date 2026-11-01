"""
📨 Group invites: a group's admin invites someone, and they can come in without asking (private groups too).

    group["invites"] = {"ben": {"by": "adi", "at": 1730000000.0}}    (saved with the group)

An invite works for GROUP_INVITE_HOURS, and only while the admin who sent it is still an admin. The invited person
gets a card: the usual msg packet with an optional "group_invite" field ({group, name, from, expires}), so old
apps show the text. Accept is /join name, Decline is /invites decline name. When an invite is over, they get
{"type": "invite_closed", "group": key, "why": "accepted" | "declined" | "expired" | "gone"}.
"""
import math
import time

from chatserver import config, profiles, resume, rooms, state, ventures_store

LIFETIME = config.GROUP_INVITE_HOURS * 3600


def is_alive(invite, group, now=None):
    """Not too old, and its admin is still an admin (a demoted admin's invites stop working)."""
    now = time.time() if now is None else now
    return now - invite["at"] < LIFETIME and invite["by"] in state.accounts and rooms.is_admin(group, invite["by"])


def hours_left(invite, now=None):
    now = time.time() if now is None else now
    return max(1, math.ceil((invite["at"] + LIFETIME - now) / 3600))


def tidy(key, group):
    """Forget the invites that ended by themselves, and close their cards."""
    for invitee in [k for k, invite in group["invites"].items() if not is_alive(invite, group)]:
        del group["invites"][invitee]
        close_card(invitee, key, "expired")
    for invitee in [k for k in group["invites"] if k not in state.accounts]:   # (an account that's gone)
        del group["invites"][invitee]


def close_card(invitee, key, why):
    packet = {"type": "invite_closed", "group": key, "why": why}
    if invitee in state.online:
        state.online[invitee].send(packet)
    else:
        resume.record_to_away(invitee, packet)


def send_card(key, group, invitee):
    invite = group["invites"][invitee]
    name, title = group["name"], rooms.room_title(key)
    extra, seat = company_card(key, invitee)
    rooms.tell(invitee, f"📨 {rooms.shown(invite['by'])} invited you to {title}{seat}! "
                        f"/join {name} to come in, or /invites decline {name}", "event",
               group_invite={"group": key, "name": name, "from": rooms.nick(invite["by"]),
                             "expires": int(invite["at"] + LIFETIME)}, **extra)


def company_card(key, invitee):
    """🏢 An invite to a company also says the seat and the equity: ({"company_invite": {...}}, " as 🛠️ CTO ...")."""
    co = ventures_store.of_group(key)
    if co is None or co["status"] != "alive":
        return {}, ""
    offer = co["offers"].get(invitee, {"role": "engineer", "bp": 0})
    icon, role_name, _ = config.ROLES[offer["role"]]
    equity = f" with {offer['bp'] / 100:g}% of the company" if offer["bp"] else ""
    card = {"company": co["id"], "name": co["name"], "sector": co["sector"], "role": offer["role"], "equity_bp": offer["bp"]}
    return {"company_invite": card}, f" (the startup) as {icon} {role_name}{equity}"


def refusal(client, key, group, target):
    """Why this invite can't be sent, or None."""
    if target == client.key:
        return "🙃 You can't invite yourself."
    if target in group["members"]:
        return f"{rooms.nick(target)} is already in {rooms.room_title(key)}."
    if target in group["banned"]:
        return f"🚫 {rooms.nick(target)} is banned from {rooms.room_title(key)}. /unban them first."
    old = group["invites"].get(target)
    if old and time.time() - old["at"] < config.GROUP_REINVITE_SECONDS:   # a fresh card every second would be spam
        return f"📨 You just invited {rooms.nick(target)}. Wait a minute before you send it again."
    if old is None and len(group["invites"]) >= config.GROUP_INVITES_MAX:
        return f"📨 {rooms.room_title(key)} already has {config.GROUP_INVITES_MAX} waiting invites. Wait for some answers."
    elsewhere = sum(1 for k, g in state.groups.items() if k != key and target in g["invites"]
                    and is_alive(g["invites"][target], g))
    if old is None and elsewhere >= config.GROUP_INVITES_PER_PERSON:
        return f"📨 {rooms.nick(target)} already has {elsewhere} group invites waiting. Let them answer those first."
    return profiles.dm_refusal(client.key, target, "group invites")   # 🔕 "who can message me"


def invite(client, key, group, target):
    """/invite name (an admin, in the group's chat). A second invite to the same person starts the 24 hours again."""
    tidy(key, group)
    why_not = refusal(client, key, group, target)
    if why_not:
        client.say(why_not, "error")
        return False
    group["invites"][target] = {"by": client.key, "at": time.time()}
    send_card(key, group, target)
    client.say(f"📨 Invited {rooms.shown(target)} to {rooms.room_title(key)}. "
               f"The invite lasts {config.GROUP_INVITE_HOURS} hours.")
    return True


def take(client, key, group):
    """/join with an invite: you're in (no request needed). Returns False when there's no invite that works."""
    tidy(key, group)
    invite = group["invites"].pop(client.key, None)
    if invite is None:
        return False
    if client.key in group["requests"]:
        group["requests"].remove(client.key)
    group["members"].append(client.key)
    close_card(client.key, key, "accepted")
    rooms.notify_room(key, f"📨 {rooms.shown(client.key)} joined {rooms.room_title(key)}, "
                           f"invited by {rooms.shown(invite['by'])}")
    return True


def decline(client, key, group):
    tidy(key, group)
    invite = group["invites"].pop(client.key, None)
    if invite is None:
        client.say(f"❓ You have no invite to {rooms.room_title(key)}.", "error")
        return False
    close_card(client.key, key, "declined")
    client.say(f"👎 You said no to {rooms.room_title(key)}.")
    rooms.tell(invite["by"], f"📨 {rooms.shown(client.key)} said no to the invite to {rooms.room_title(key)}.")
    return True


def withdraw(key, group, target, why="gone"):
    """A ban or a kick ("gone"), or they got in another way ("accepted"): their invite goes, so an old one can't
    bring a kicked member back later."""
    if group["invites"].pop(target, None) is not None:
        close_card(target, key, why)


def close_all(key, group):
    """The group is going away (/disband)."""
    for invitee in list(group["invites"]):
        close_card(invitee, key, "gone")
    group["invites"].clear()


def mine(login):
    """[(key, group, invite)] that are still waiting for this person, oldest group name first."""
    found = []
    for key in sorted(state.groups):
        group = state.groups[key]
        tidy(key, group)
        if login in group["invites"]:
            found.append((key, group, group["invites"][login]))
    return found


def deliver_at_login(login):
    """Invites that came while you were away: their cards again."""
    for key, group, _ in mine(login):
        send_card(key, group, login)


def admin_list(group):
    """For the Groups screen (admins only): who's invited, and for how much longer."""
    now = time.time()
    return [{"name": rooms.nick(k), "hours_left": hours_left(invite, now)}
            for k, invite in group["invites"].items() if k in state.accounts and is_alive(invite, group, now)]


def clean_saved(value):
    """The invites read from chat_data.json, keeping only well-formed ones that haven't ended."""
    if not isinstance(value, dict):
        return {}
    now, kept = time.time(), {}
    for invitee, invite in value.items():
        if not (isinstance(invitee, str) and isinstance(invite, dict) and isinstance(invite.get("by"), str)):
            continue
        at = invite.get("at")
        if isinstance(at, (int, float)) and not isinstance(at, bool) and 0 <= now - at < LIFETIME:
            kept[invitee] = {"by": invite["by"], "at": at}
    return kept
