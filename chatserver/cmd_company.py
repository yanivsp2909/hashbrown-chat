"""
🏢 /company: found a startup, see its numbers, spend today's action points, run the team (docs/VENTURES.md).
You can be in one company at a time, so /company works from any room.
"""
import random
import time

from chatserver import (cap_table, config, fund, registry, rooms, state, storage, ventures_actions, ventures_angels, ventures_news, ventures_rounds,
                        ventures_sim, ventures_store, ventures_team, ventures_tick)
from chatserver.ventures_text import money, runway_text, sector_title, stage_name, whole

USAGE = ("Usage: /company found name sector · /company (status) · /company actions · /company <action> · "
         "/company info name · report · captable · team · invite · role · grant · ceo · fire · leave · shutdown · "
         "bridge · angels")


@registry.command("/company", "/company [found name sector | action | info name ...]",
                  "🏢 your startup: found it, grow it, raise money", "🏢 Ventures")
def cmd_company(client, args):
    sub, _, rest = args.strip().partition(" ")
    sub, rest = sub.lower(), rest.strip()
    if sub == "found":
        return found(client, rest)
    if sub == "info":
        return info(client, rest)
    if sub in ("help", "?"):
        return client.say(USAGE)
    co = ventures_team.saw(client.key)   # (you're here: maybe an action point for the team)
    if co is None:
        return client.say("🏢 You're not in a company. Found one: /company found name sector "
                          f"(sectors: {', '.join(config.SECTORS)}). The board: /ventures",
                          "error" if sub else "system")
    if sub == "":
        return client.say(status_text(co))
    if ventures_actions.is_action(co, sub):
        return act(client, co, sub, rest)
    handler = TEAM.get(sub) or FUNDING.get(sub)
    if handler is None:
        return client.say(USAGE, "error")
    handler(client, co, rest)


# ---------------------------------------------------------------- founding

def found(client, args):
    parts = args.split()
    if len(parts) < 2:
        return client.say(f"Usage: /company found name sector   (sectors: {', '.join(config.SECTORS)})", "error")
    why_not = found_refusal(client.key, parts[0], parts[1].lower())
    if why_not:
        return client.say(why_not, "error")
    name, key, sector = parts[0], parts[0].lower(), parts[1].lower()
    account = state.accounts[client.key]
    account["tokens"] -= config.FOUND_COST
    fund.collect(config.FOUND_COST, "found")
    cid = ventures_store.next_id()
    co = ventures_store.put(ventures_store.new_company(cid, name, key, sector, client.key, ventures_store.ensure()["tick"]))
    group = storage.new_group(name, client.key, True)
    state.groups[key] = {**group, "company": cid, "emoji": config.SECTORS[sector]["icon"]}
    client.say(f"🏢 Founded {name} ({sector_title(sector)}) for {config.FOUND_COST} 🪙! It's a private group with "
               f"{money(config.START_CASH)} of founders' savings. Invite co-founders with /company invite name role "
               f"[equity%], and spend today's {co['ap']} action points: /company actions", "event")
    rooms.announce(f"🏢 New startup: {name} ({sector_title(sector)}) by {rooms.shown(client.key)}", exclude={client.key})
    ventures_news.add("founded", f"🏢 New startup: {name} ({sector_title(sector)}) by {rooms.nick(client.key)}", co)
    rooms.move_to_room(client, key)
    rooms.send_room_list(client.key)
    ventures_team.send_event(co, "founded", f"🏢 {name} was founded.")
    storage.save_data()


def found_refusal(login, name, sector):
    if not rooms.valid_name(name) or name.lower() == "lobby":
        return f"❌ Company names: {rooms.NAME_RULE}"
    if name.lower() in state.groups:
        return "❌ That name is taken (by a group or a company)."
    if sector not in config.SECTORS:
        return f"Sectors: {', '.join(f'{k} ({sector_title(k)})' for k in config.SECTORS)}"
    return person_refusal(login)


def person_refusal(login):
    """Why this person can't found a company now, whatever its name (the website's "Start a company" asks too)."""
    other = ventures_store.mine(login)
    if other:
        return f"🏢 You're already in {other['name']}. One company at a time (you can still /invest in others)."
    account = state.accounts[login]
    if time.time() - account.get("created", 0) < config.VENTURES_MIN_AGE_HOURS * 3600:
        return f"🏢 Your account must be {config.VENTURES_MIN_AGE_HOURS} hours old to found a company."
    wait = ventures_store.ensure()["cooldowns"].get(login, 0) - ventures_store.ensure()["tick"]
    if wait > 0:
        return f"⏳ Your last company just closed: wait {wait} more day{'s' if wait > 1 else ''} before you found another."
    if account["tokens"] < config.FOUND_COST:
        return f"💸 Founding a company costs {config.FOUND_COST} 🪙, you have {account['tokens']}."
    return None


# ---------------------------------------------------------------- looking

def status_text(co):
    players = len(ventures_store.members(co))
    staff = co["staff"]
    lines = [f"🏢 {co['name']} · {sector_title(co['sector'])} · {stage_name(co['stage'])} · day {co['stage_ticks']} "
             f"of this stage",
             f"💵 Cash {money(co['cash'])} · 🔥 burn {money(ventures_sim.burn(co, players))}/day · "
             f"📈 MRR {money(ventures_sim.revenue(co))} · ⏳ runway {runway_text(ventures_sim.runway(co, players))} · "
             f"💎 valuation {money(co['valuation'])}",
             f"👥 {whole(co['customers'])} {config.SECTORS[co['sector']]['customers']} · ⭐ quality {co['quality']:.0f} · "
             f"📣 hype {co['hype']:.0f} · 🤝 reputation {co['reputation']:.0f} · 🧑‍💼 staff {ventures_sim.staff_total(co)} "
             f"({staff['engineer']} engineer{'s' if staff['engineer'] != 1 else ''}, {staff['sales']} sales, "
             f"{staff['marketer']} marketer{'s' if staff['marketer'] != 1 else ''})",
             team_line(co)]
    if co["fumes"]:
        lines.append("🚨 ON FUMES: out of cash. Raise money (/pitch, /company bridge) or cut costs before the next tick!")
    lines.append(ventures_tick.next_round_line(co, players, "left today: /company actions."))
    lines.extend(ventures_rounds.status_lines(co))
    return "\n".join(lines)


def team_line(co):
    people = []
    for login in ventures_store.members(co):
        role = co["roles"].get(login, "engineer")
        dot = "🟢" if login in state.online else "⚫"
        people.append(f"{dot} {rooms.shown(login)} ({ventures_team.role_title(role)})")
    return " · ".join(people)


def info(client, args):
    co = ventures_store.find(args) if args else ventures_store.mine(client.key)
    if co is None:
        return client.say(f"❓ No company called {args}. See /ventures" if args else "Usage: /company info name", "error")
    rounds = ", ".join(f"{stage_name(r['stage'])} {money(r['amount'])}" for r in co["rounds"]) or "none yet"
    state_word = {"alive": "", "dead": " · ⚰️ dead", "shutdown": " · 🪦 shut down"}[co["status"]]
    client.say(f"🏢 {co['name']} · {sector_title(co['sector'])} · {stage_name(co['stage'])}{state_word}\n"
               f"💎 valuation {money(co['valuation'])} · {co['age']} days old · rounds: {rounds}\n"
               f"👥 {team_line(co)}")


def actions(client, co, args):
    lines = [f"⚡ {co['name']}: {co['ap']} action points left today (they refill at the daily tick, "
             f"{config.VENTURES_TICK_HOUR}:00 Israel time)."]
    for row in ventures_actions.menu(co):
        price = f", {money(row['cost'])}" if row["cost"] else ""
        mark = "  " if row["ok"] else "  🚫 "
        why = f"  ({row['why']})" if row["why"] else ""
        lines.append(f"{mark}/company {row['usage']}  [{row['ap']} AP{price}]  {row['help']}{why}")
    lines.append(f"  /pitch  [{config.PITCH_AP} AP]  🎤 pitch an investor (needs the next round's milestones)")
    client.say("\n".join(lines))


def report(client, co, args):
    client.say(co["report"] or f"📊 No report yet: the first comes at the daily tick ({config.VENTURES_TICK_HOUR}:00 Israel time).")


def captable(client, co, args):
    lines = [f"📜 Who owns {co['name']}:"]
    for holder, bp in sorted(co["cap"].items(), key=lambda item: -item[1]):
        lines.append(f"  {holder_name(holder)}  {cap_table.percent_text(bp)}")
    client.say("\n".join(lines))


def holder_name(holder):
    if holder == cap_table.POOL:
        return "📜 Option pool"
    if holder.startswith("p:"):
        return f"👤 {rooms.nick(holder[2:])}" if holder[2:] in state.accounts else f"👤 {holder[2:]}"
    return ventures_rounds.investor_title(holder[2:])


def team(client, co, args):
    client.say(f"👥 {co['name']}: {team_line(co)}")


# ---------------------------------------------------------------- doing things

def act(client, co, name, args):
    try:
        new, text = ventures_actions.apply(co, name, args, random.Random(), ventures_store.ensure()["tick"])
    except ventures_actions.ActionError as e:
        return client.say(str(e), "error")
    ventures_store.put(new)
    left = "1 action point" if new["ap"] == 1 else f"{new['ap']} action points"
    line = f"⚡ {rooms.shown(client.key)}: {text} ({left} left today)"
    ventures_team.tell_company(new, line)
    if client.room != co["group"]:
        client.say(line)
    storage.save_data()


TEAM = {"actions": actions, "report": report, "captable": captable, "team": team,
        "invite": ventures_team.invite, "role": ventures_team.set_role, "grant": ventures_team.grant,
        "ceo": ventures_team.hand_over, "fire": ventures_team.fire,
        "leave": lambda client, co, args: ventures_team.leave(client, co), "shutdown": ventures_team.shutdown}
FUNDING = {"bridge": ventures_rounds.bridge, "angels": ventures_angels.list_angels, "angel": ventures_angels.answer}
