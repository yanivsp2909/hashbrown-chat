"""
🏢 What the website's Ventures screens show: the home (my company, the Unicorn Board, the graveyard, my investments)
and one company's HQ. These packets only SHOW things: every button sends an existing /command, so the commands'
own checks stay the only rules (like group_view.py for the Groups screen).

    browser -> server: {"type": "get_ventures"}                  the home (and keep it fresh while it's open)
                       {"type": "get_company", "company": "c3"}  one company's HQ (and keep it fresh)
                       {"type": "ventures_closed"}               the screen closed: no more updates
    server -> browser: {"type": "ventures", ...home}   {"type": "company", "company": {...}}

Privacy: a company's cash, numbers, actions, reports, pitch and term sheet only go to its members. Everyone
sees the name, sector, stage, valuation, team, owners (the cap table) and funding rounds.
Old clients never send get_ventures, so they never get any of this.
"""
import json
import time
import traceback

from chatserver import (cap_table, config, rooms, state, textutil, ventures_actions, ventures_angels, ventures_events,
                        ventures_log, ventures_news, ventures_pitch, ventures_rounds, ventures_sectors, ventures_sim,
                        ventures_store, ventures_team, ventures_tick)
from chatserver.ventures_text import stage_name

FORCE_EVERY = 10   # seconds: even with nothing changed, refresh (online dots, the countdown's clock)
_last_force = [0.0]


# ---------------------------------------------------------------- the home

def summary(co):
    sector = config.SECTORS[co["sector"]]
    return {"id": co["id"], "name": co["name"], "sector": co["sector"], "icon": sector["icon"], "stage": co["stage"],
            "stage_name": stage_name(co["stage"]), "status": co["status"], "valuation": co["valuation"],
            "age": co["age"], "fumes": co["fumes"], "team": [rooms.nick(k) for k in ventures_store.members(co)]}


def sectors():
    return [{"key": key, "icon": info["icon"], "name": info["name"], "customers": info["customers"],
             "pitch": config.SECTOR_CARDS[key][0], "twist": config.SECTOR_CARDS[key][1],
             "difficulty": config.SECTOR_CARDS[key][2]} for key, info in config.SECTORS.items()]


def home(viewer):
    ventures = ventures_store.ensure()
    mine = ventures_store.mine(viewer)
    board = sorted(ventures_store.alive(), key=lambda c: -c["valuation"])[:20]
    return {"type": "ventures",
            "season": {"number": ventures["season"], "day": ventures["tick"], "days": config.SEASON_TICKS,
                       "next_tick": ventures_tick.next_tick_at()},
            "me": {"tokens": state.accounts[viewer]["tokens"], "found_cost": config.FOUND_COST,
                   "can_found": mine is None and found_refusal(viewer) is None,
                   "why": "" if mine else (found_refusal(viewer) or "")},
            "mine": summary(mine) if mine else None,
            "board": [summary(co) for co in board],
            "graveyard": list(reversed(ventures["graveyard"][-20:])),
            "news": ventures_news.feed(limit=20),
            "investments": investments(viewer),
            "invites": company_invites(viewer),
            "sectors": sectors(),
            "roles": [{"key": k, "icon": v[0], "name": v[1], "c_level": v[2]} for k, v in config.ROLES.items()]}


def found_refusal(viewer):
    """Why this person can't found now (the same checks as /company found, without the name and sector)."""
    from chatserver.cmd_company import person_refusal   # (cmd_company is loaded by then)
    return person_refusal(viewer)


def investments(viewer):
    """Companies I own a piece of but don't work at, and my angel offers still waiting."""
    holder = cap_table.player(viewer)
    held = [{**summary(co), "bp": co["cap"][holder], "tokens": co["angel_in"].get(viewer, 0)}
            for co in ventures_store.companies().values()
            if holder in co["cap"] and viewer not in ventures_store.members(co)]
    waiting = [{"company": o["company"], "name": (ventures_store.get(o["company"]) or {}).get("name", "?"),
                "tokens": o["tokens"], "bp": o.get("bp", 0)}
               for o in ventures_angels.offers().values() if o["login"] == viewer]
    return {"held": held, "waiting": waiting}


def company_invites(viewer):
    """Company invites waiting for me (the Accept / Decline card)."""
    found = []
    for key, group in state.groups.items():
        co = ventures_store.of_group(key)
        invite = group["invites"].get(viewer)
        if co and co["status"] == "alive" and invite:
            offer = ventures_team.offer_for(co, viewer, invite["at"])
            found.append({"company": co["id"], "name": co["name"], "group": group["name"], "role": offer["role"],
                          "bp": offer["bp"], "from": rooms.nick(invite["by"])})
    return found


# ---------------------------------------------------------------- one company's HQ

def public(co, viewer):
    sector = config.SECTORS[co["sector"]]
    return {**summary(co), "sector_name": sector["name"], "customer_word": sector["customers"], "cause": co["cause"],
            "stage_ticks": co["stage_ticks"], "peak": co["peak"], "raised": co["raised"],
            "rounds": [{**r, "stage_name": stage_name(r["stage"]) if r["stage"] in config.STAGE_NAMES else "Bridge",
                        "investor_name": ventures_rounds.investor_title(r["investor"])} for r in co["rounds"]],
            "team": team(co), "cap": cap(co), "timeline": timeline(co), "member": viewer in ventures_store.members(co),
            "you": you(co, viewer), "news": ventures_news.feed(co["id"], 8),
            "sector_panel": ventures_sectors.panel(co, {"tick": ventures_store.ensure()["tick"],
                                                        "companies": ventures_store.alive()}),
            "events": [{"headline": e["headline"], "until": e["until"]} for e in ventures_events.active()
                       if e.get("sector") in (co["sector"], "all") or e.get("company") == co["id"]]}


def team(co):
    rows = []
    for login in ventures_store.members(co):
        role = co["roles"].get(login, "engineer")
        icon, name, c_level = config.ROLES[role]
        rows.append({"name": rooms.nick(login), "role": role, "role_title": f"{icon} {name}", "c_level": c_level,
                     "online": login in state.online, "bp": co["cap"].get(cap_table.player(login), 0)})
    return rows


def cap(co):
    rows = []
    for holder, bp in sorted(co["cap"].items(), key=lambda item: -item[1]):
        if holder == cap_table.POOL:
            kind, name = "pool", "Option pool"
        elif holder.startswith("p:"):
            login = holder[2:]
            kind, name = "player", rooms.nick(login) if login in state.accounts else login
        else:
            kind, name = "investor", ventures_rounds.investor_title(holder[2:])
        rows.append({"name": name, "kind": kind, "bp": bp})
    return rows


def timeline(co):
    stages = config.STAGES
    now = stages.index(co["stage"])
    return [{"stage": s, "name": "IPO" if s == "public" else stage_name(s),
             "state": "done" if i < now else "now" if i == now else "next" if i == now + 1 else "later"}
            for i, s in enumerate(stages)]


def you(co, viewer):
    holder = cap_table.player(viewer)
    waiting = next((o for o in ventures_angels.waiting_for(co) if o["login"] == viewer), None)
    why = invest_refusal(co, viewer)
    return {"role": co["roles"].get(viewer, ""), "ceo": ventures_team.ceo_of(co) == viewer,
            "c_level": ventures_team.is_c_level(co, viewer), "bp": co["cap"].get(holder, 0),
            "angel_waiting": {"tokens": waiting["tokens"], "bp": waiting.get("bp", 0)} if waiting else None,
            "can_invest": why is None, "invest_why": why or "",
            "invest_min": config.ANGEL_MIN, "invest_max": config.ANGEL_MAX_PER_COMPANY}


def invest_refusal(co, viewer):
    if co["status"] != "alive" or co["stage"] not in config.ANGEL_STAGES:
        return "Angels invest only in live Idea, Pre-seed and Seed companies."
    return ventures_angels.refusal(viewer, co, co["name"], config.ANGEL_MIN)


def inside(co, viewer):
    """What only the team sees."""
    players = len(ventures_store.members(co))
    staff = co["staff"]
    numbers = {"cash": co["cash"], "burn": int(ventures_sim.burn(co, players)), "revenue": int(ventures_sim.revenue(co)),
               "runway": ventures_sim.runway(co, players), "customers": co["customers"], "quality": co["quality"],
               "hype": co["hype"], "reputation": co["reputation"], "staff": staff,
               "staff_total": ventures_sim.staff_total(co), "staff_max": ventures_sim.stage(co)["staff_max"]}
    return {"numbers": numbers, "history": ventures_log.days(co["id"]), "ap": co["ap"], "ap_max": config.AP_MAX,
            "next_tick": ventures_tick.next_tick_at(), "fumes": co["fumes"], "actions": actions(co),
            "reports": list(reversed(co["reports"])), "milestones": milestones(co, players),
            "pitch": pitch(co, viewer, players), "sheet": sheet(co), "angels": angels(co),
            "invites_out": invites_out(co), "bridge": bridge(co, viewer), "interest": interest(co, players)}


def actions(co):
    rows = ventures_actions.menu(co)
    lines = ventures_sectors.state(co).get("lines", {})
    choices = {"hire": list(ventures_store.STAFF_KINDS), "layoff": [k for k in ventures_store.STAFF_KINDS if co["staff"][k]],
               "pivot": list(config.SECTORS), "compute": ["10", "50", "200"], "manufacture": ["100", "300", "1000"],
               "launch": [k for k, level in lines.items() if level == 0] if co["sector"] == "cyber" else [],
               "improve": [k for k, level in lines.items() if level > 0]}
    return [{**r, "choices": choices.get(r["name"], [])} for r in rows]


def milestones(co, players):
    return [{**r, "text": ventures_tick.milestone_text(r)} for r in ventures_sim.milestones(co, players)]


def interest(co, players):
    if co["stage"] not in config.ROUNDS or co["stage"] == "c":
        return {"level": "", "text": ""}
    points = ventures_rounds.score(co, 5, players)
    level = "low" if points < config.PASS_BELOW else "fair" if points < 0.5 else "hot"
    return {"level": level, "text": ventures_rounds.interest(co, players)}


def pitch(co, viewer, players):
    why = ventures_pitch.refusal(viewer, co)
    live = co["pitch"]
    investor = (live or {}).get("investor") or co["last_investor"]
    info = ventures_rounds.INVESTORS.get(investor) if investor else None
    return {"active": bool(live), "busy": bool(live and live["busy"]), "turn": live["turn"] if live else 0,
            "questions": config.PITCH_QUESTIONS, "can_pitch": why is None, "why": why or "",
            "pitches_left": max(0, config.PITCHES_PER_STAGE - co["pitches"]), "ap_cost": config.PITCH_AP,
            "investor": {"id": investor, "name": info["name"], "firm": info["firm"], "emoji": info["emoji"]} if info else None,
            "log": co["pitch_log"]}


def sheet(co):
    if not co["sheet"]:
        return None
    return {**ventures_rounds.card(co["sheet"])[1], "message": co["sheet"].get("message", "")}


def angels(co):
    rows = []
    for o in ventures_angels.waiting_for(co):
        dollars, bp = ventures_angels.terms(co, o)
        rows.append({"name": rooms.nick(o["login"]), "tokens": o["tokens"], "dollars": dollars, "bp": bp})
    return rows


def invites_out(co):
    group = state.groups.get(co["group"])
    if not group:
        return []
    rows = []
    for login, invite in group["invites"].items():
        offer = ventures_team.offer_for(co, login, invite["at"])
        rows.append({"name": rooms.nick(login), "role": offer["role"], "bp": offer["bp"]})
    return rows


def bridge(co, viewer):
    if co["stage"] not in config.ROUNDS:
        return {"ok": False, "why": "", "amount": 0, "bp": 0}
    amount, _, bp = ventures_rounds.bridge_terms(co)
    why = ("Only the CEO takes a bridge round." if ventures_team.ceo_of(co) != viewer
           else "Once per stage." if co["bridged"] == co["stage"]
           else "Only when on fumes or out of pitches." if not (co["fumes"] or co["pitches"] >= config.PITCHES_PER_STAGE)
           else "")
    return {"ok": not why, "why": why, "amount": amount, "bp": bp}


def company_packet(co, viewer):
    body = public(co, viewer)
    if body["member"]:
        body = {**body, **inside(co, viewer)}
    return {"type": "company", "company": body}


# ---------------------------------------------------------------- sending

def send_view(client, force=True):
    if client.ventures_view is None or client.key is None:
        return
    packets = [home(client.key)]
    co = ventures_store.get(client.ventures_view) if client.ventures_view else None
    if co:
        packets.append(company_packet(co, client.key))
    for packet in packets:
        text = json.dumps(packet, sort_keys=True)
        if force or client.ventures_sent.get(packet["type"]) != text:
            client.ventures_sent[packet["type"]] = text
            client.send(packet)


def handle(client, msg):
    kind = msg.get("type")
    if kind == "ventures_closed":
        client.ventures_view = None
        client.ventures_sent = {}
        return
    if kind == "get_ventures":
        client.ventures_view = ""
    else:
        cid = msg.get("company")
        if not isinstance(cid, str) or ventures_store.get(cid) is None:
            client.say("🏢 No company like that.", "error")
            return
        client.ventures_view = cid
    send_view(client)


def push_updates():
    """Called every second: if something changed (or every FORCE_EVERY s), the open Ventures screens refresh."""
    now = time.time()
    if not state.ventures_dirty and now - _last_force[0] < FORCE_EVERY:
        return
    state.ventures_dirty = False
    _last_force[0] = now
    for client in list(state.online.values()):
        try:
            send_view(client, force=False)
        except Exception:   # one broken view mustn't stop everyone else's
            textutil.log("[VENTURES] Error while refreshing a Ventures screen:\n" + traceback.format_exc())
