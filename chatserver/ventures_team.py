"""
👥 A company's team: roles (CEO, CTO...), equity grants with vesting, invites, leaving, firing, handing over the
CEO seat, shutting down, and the hooks the group code calls (a company IS a private group: the CEO is its owner,
the C-level seats are its admins). docs/VENTURES.md, section 2.
"""
from chatserver import cap_table, config, history, invites, rooms, state, storage, ventures_store, ventures_text

C_LEVEL = [role for role, (_, _, is_c) in config.ROLES.items() if is_c]


def role_title(role):
    icon, name, _ = config.ROLES[role]
    return f"{icon} {name}"


def ceo_of(co):
    return next((login for login, role in co["roles"].items() if role == "ceo"), co["founder"])


def is_c_level(co, login):
    return co["roles"].get(login) in C_LEVEL


def holder_for_returns(co):
    """Unvested equity goes back to the option pool, or to the CEO before there is one."""
    return cap_table.POOL if cap_table.POOL in co["cap"] else cap_table.player(ceo_of(co))


# ---------------------------------------------------------------- telling the company

def tell_company(co, text, kind="event", exclude=None):
    """A line for whoever is in the company's chat right now."""
    rooms.notify_room(co["group"], text, exclude=exclude, kind=kind)


def post_to_company(co, text, badge="📊"):
    """A line that stays in the company chat's history (the daily report, the investors' lines)."""
    msg = rooms.chat_message("Ventures", badge, text)
    history.add(co["group"], msg)
    rooms.send_room(co["group"], msg)


def send_event(co, kind, text):
    """{"type": "company_event"} for members whose app understands Ventures (the website)."""
    packet = {"type": "company_event", "company": co["id"], "kind": kind, "text": text}
    for login in ventures_store.members(co):
        client = state.online.get(login)
        if client and "ventures" in client.features:
            client.send(packet)


# ---------------------------------------------------------------- action points: friends who show up

def saw(login):
    """A member is online (login, or a /company command): the first time today, another player adds a point."""
    co = ventures_store.mine(login)
    if co is None or login in co["seen"]:
        return co
    bonus = 1 if co["seen"] else 0
    return ventures_store.put({**co, "seen": co["seen"] + [login], "ap": min(config.AP_MAX, co["ap"] + bonus)})


def on_login(login):
    co = saw(login)
    if co and co["fumes"]:
        rooms.tell(login, f"🚨 {co['name']} is out of cash and on fumes! Raise money or cut costs before "
                          f"the next tick. /company", "error")


# ---------------------------------------------------------------- joining (group invites)

def invite(client, co, args):
    """/company invite name role [equity%]."""
    parts = args.split()
    if len(parts) < 2 or parts[1].lower() not in config.ROLES:
        return client.say(f"Usage: /company invite name role [equity%]   (roles: {', '.join(config.ROLES)})", "error")
    target, role = rooms.find_account(parts[0]), parts[1].lower()
    bp = percent_to_bp(parts[2]) if len(parts) > 2 else 0
    why_not = invite_refusal(client.key, co, target, role, bp, parts[0])
    if why_not:
        return client.say(why_not, "error")
    group = state.groups[co["group"]]
    ventures_store.put({**co, "offers": {**co["offers"], target: {"role": role, "bp": bp}}})   # (the card shows it)
    if invites.invite(client, co["group"], group, target):
        storage.save_data()
    else:
        ventures_store.put(co)   # not sent: the offer goes too


def invite_refusal(inviter, co, target, role, bp, name):
    if not is_c_level(co, inviter):
        return "🛡️ Only the CEO and the C-level team can invite."
    if target is None:
        return f"❓ No user called {name}."
    if bp is None or bp < 0:
        return "Equity is a percent, like 10 or 2.5"
    if (role in C_LEVEL or bp) and ceo_of(co) != inviter:
        return "👑 Only the CEO can offer a C-level seat or equity."
    if role in C_LEVEL and role in co["roles"].values():
        return f"{co['name']} already has a {config.ROLES[role][1]}."
    if bp > cap_table.share(co["cap"], cap_table.player(inviter)):
        return f"📜 You own {cap_table.percent_text(cap_table.share(co['cap'], cap_table.player(inviter)))}."
    if len(ventures_store.members(co)) >= config.TEAM_MAX_PLAYERS:
        return f"👥 A company has at most {config.TEAM_MAX_PLAYERS} players."
    return None


def percent_to_bp(text):
    try:
        value = float(text.rstrip("%"))
    except ValueError:
        return None
    return int(round(value * 100)) if 0 <= value <= 100 else None


def join_refusal(login, key):
    """Why this person can't come into a company group now (None: they can). Called by /join."""
    co = ventures_store.of_group(key)
    if co is None or co["status"] != "alive":
        return None
    other = ventures_store.mine(login)
    if other and other["id"] != co["id"]:
        return f"🏢 You're already in {other['name']}. One company at a time (you can still /invest in others)."
    if login not in state.groups[key]["invites"]:
        return f"🏢 {co['name']} is a company: ask its CEO for an invite."
    if len(ventures_store.members(co)) >= config.TEAM_MAX_PLAYERS:
        return f"👥 {co['name']} already has {config.TEAM_MAX_PLAYERS} players."
    return None


def joined(login, key):
    """They just came in with an invite: their role and equity, as offered."""
    co = ventures_store.of_group(key)
    if co is None or co["status"] != "alive":
        return
    offer = co["offers"].get(login, {"role": "engineer", "bp": 0})
    role = offer["role"] if not (offer["role"] in C_LEVEL and offer["role"] in co["roles"].values()) else "engineer"
    cap, grants = co["cap"], co["grants"]
    if offer["bp"]:
        cap = cap_table.move(cap, cap_table.player(ceo_of(co)), cap_table.player(login), offer["bp"])
        grants = {**grants, login: {"bp": cap_table.share(cap, cap_table.player(login)), "tick": co["age"]}}
    offers = {k: v for k, v in co["offers"].items() if k != login}
    co = ventures_store.put({**co, "roles": {**co["roles"], login: role}, "cap": cap, "grants": grants, "offers": offers})
    set_admin(key, login, role in C_LEVEL)
    saw(login)
    equity = f" with {cap_table.percent_text(offer['bp'])}" if offer["bp"] else ""
    tell_company(co, f"🎉 {rooms.shown(login)} joined {co['name']} as {role_title(role)}{equity}!")
    rooms.tell(login, f"🎉 You joined {co['name']} as {role_title(role)}{equity}. /company shows the numbers, "
                      f"/company actions what you can do today.", "event")


def set_admin(key, login, admin):
    group = state.groups[key]
    admins = [a for a in group["admins"] if a != login] + ([login] if admin else [])
    state.groups[key] = {**group, "admins": admins}


# ---------------------------------------------------------------- the CEO's tools

def set_role(client, co, args):
    parts = args.split()
    if len(parts) != 2 or parts[1].lower() not in config.ROLES or parts[1].lower() == "ceo":
        return client.say("Usage: /company role name role   (roles: cto, cfo, cmo, coo, engineer, designer, sales; "
                          "the CEO seat: /company ceo name)", "error")
    target, role = member_named(client, co, parts[0]), parts[1].lower()
    if target is None:
        return
    if target == ceo_of(co):
        return client.say("👑 The CEO stays CEO. Hand the seat over with /company ceo name.", "error")
    if role in C_LEVEL and role in co["roles"].values():
        return client.say(f"{co['name']} already has a {config.ROLES[role][1]}.", "error")
    co = ventures_store.put({**co, "roles": {**co["roles"], target: role}})
    set_admin(co["group"], target, role in C_LEVEL)
    storage.save_data()
    tell_company(co, f"🎖️ {rooms.shown(target)} is now {role_title(role)}.")


def grant(client, co, args):
    parts = args.split()
    bp = percent_to_bp(parts[1]) if len(parts) == 2 else None
    if not bp:
        return client.say("Usage: /company grant name percent   (from your own shares)", "error")
    target = member_named(client, co, parts[0])
    if target is None:
        return
    mine = cap_table.share(co["cap"], cap_table.player(client.key))
    if target == client.key or bp > mine:
        return client.say(f"📜 You can give from your own {cap_table.percent_text(mine)}.", "error")
    cap = cap_table.move(co["cap"], cap_table.player(client.key), cap_table.player(target), bp)
    old = co["grants"].get(target, {"bp": 0, "tick": co["age"]})
    co = ventures_store.put({**co, "cap": cap, "grants": {**co["grants"], target: {**old, "bp": old["bp"] + bp}}})
    storage.save_data()
    tell_company(co, f"📜 {rooms.shown(client.key)} gave {rooms.shown(target)} {cap_table.percent_text(bp)} of {co['name']}.")


def hand_over(client, co, args):
    target = member_named(client, co, args.strip())
    if target is None:
        return
    if target == client.key:
        return client.say("👑 You're already the CEO.", "error")
    roles = {**co["roles"], target: "ceo", client.key: co["roles"].get(target, "engineer")}
    co = ventures_store.put({**co, "roles": roles})
    group = state.groups[co["group"]]
    state.groups[co["group"]] = {**group, "owner": target}
    set_admin(co["group"], target, False)
    set_admin(co["group"], client.key, roles[client.key] in C_LEVEL)
    storage.save_data()
    tell_company(co, f"👑 {rooms.shown(target)} is the CEO of {co['name']} now.")
    if client.room != co["group"]:
        client.say(f"👑 {rooms.shown(target)} is the CEO of {co['name']} now.")


def fire(client, co, args):
    target = member_named(client, co, args.strip())
    if target is None:
        return
    if target == client.key:
        return client.say("🙃 Hand the CEO seat over first (/company ceo name), or /company shutdown name.", "error")
    remove(co, target)
    rooms.tell(target, f"👋 {co['name']}'s CEO let you go. Your vested shares are still yours.", "error")
    tell_company(ventures_store.get(co["id"]), f"👋 {rooms.shown(target)} left the team.")


def leave(client, co):
    if ceo_of(co) == client.key:
        return client.say("👑 The CEO can't just leave: /company ceo name hands the seat over, "
                          "/company shutdown name closes the company.", "error")
    remove(co, client.key)
    client.say(f"👋 You left {co['name']}. Your vested shares are still yours.")
    tell_company(ventures_store.get(co["id"]), f"👋 {rooms.shown(client.key)} left the team.")


def remove(co, login):
    """Out of the team and the group; the unvested part of their grants goes back."""
    cap = co["cap"]
    grant_ = co["grants"].get(login)
    if grant_:
        unvested = max(0, grant_["bp"] - cap_table.vested(grant_, co["age"]))
        cap = cap_table.move(cap, cap_table.player(login), holder_for_returns(co), unvested)
    roles = {k: v for k, v in co["roles"].items() if k != login}
    grants = {k: v for k, v in co["grants"].items() if k != login}
    ventures_store.put({**co, "cap": cap, "roles": roles, "grants": grants})
    key, group = co["group"], state.groups[co["group"]]
    state.groups[key] = {**group, "members": [m for m in group["members"] if m != login],
                         "admins": [a for a in group["admins"] if a != login]}
    invites.withdraw(key, state.groups[key], login)
    if login in state.online and state.online[login].room == key:
        rooms.move_to_room(state.online[login], "lobby")
    rooms.send_room_list(login)
    storage.save_data()


def shutdown(client, co, args):
    if args.strip().lower() != co["name"].lower():
        return client.say(f"⚠️ This closes {co['name']} for good. To be sure, type its name: "
                          f"/company shutdown {co['name']}", "error")
    co = ventures_store.put({**co, "status": "shutdown", "cause": "shut down by its founders"})
    bury(co, "shut down")
    tell_company(co, f"🪦 {co['name']} was shut down by {rooms.shown(client.key)}. Its chat stays as a memorial.")
    if client.room != co["group"]:
        client.say(f"🪦 {co['name']} was shut down.")
    storage.save_data()


def member_named(client, co, name):
    """A team member by name, or None (and the reason said)."""
    if ceo_of(co) != client.key:
        client.say("👑 Only the CEO can do that.", "error")
        return None
    target = rooms.find_account(name) if name else None
    if target is None or target not in ventures_store.members(co):
        client.say(f"❓ {name or '...'} isn't in {co['name']}.", "error")
        return None
    return target


# ---------------------------------------------------------------- the end

EPITAPHS = ["It moved fast and broke everything, including the bank.",
            "Gone, but its pitch deck lives on.",
            "It had a great vision and a terrible runway.",
            "Pivoted once too few times.",
            "Its investors said \"interesting\" and never called back."]


def bury(co, how):
    """A dead or closed company: a graveyard entry, and a short wait before its players found again."""
    ventures = ventures_store.ensure()
    founders = [rooms.nick(login) for login in ventures_store.members(co)]
    entry = {"id": co["id"], "name": co["name"], "sector": co["sector"], "stage": co["stage"], "founders": founders,
             "lived": co["age"], "peak": co["peak"], "raised": co["raised"], "cause": co["cause"], "how": how,
             "epitaph": EPITAPHS[int(co["id"][1:]) % len(EPITAPHS)], "season": co["season"], "tick": ventures["tick"]}
    ventures_store.set_field("graveyard", (ventures["graveyard"] + [entry])[-config.GRAVEYARD_KEPT:])
    wait_until = ventures["tick"] + config.FOUND_COOLDOWN_TICKS
    cooldowns = {**ventures_store.ensure()["cooldowns"], **{login: wait_until for login in ventures_store.members(co)}}
    ventures_store.set_field("cooldowns", cooldowns)
    rooms.announce(f"⚰️ {co['name']} ({ventures_text.sector_title(co['sector'])}) {how}: {co['cause']}. "
                   f"It lived {co['age']} days and peaked at {ventures_text.money(co['peak'])}.")
    send_event(co, "death", f"⚰️ {co['name']} {how}: {co['cause']}.")
