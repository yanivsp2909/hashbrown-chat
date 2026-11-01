"""
😇 Angel investing: a player puts personal 🪙 into an early company (Idea, Pre-seed, Seed) for shares.

The tokens are HELD (taken from the wallet, kept in the offer) until the company's CEO says yes or no, or
ANGEL_OFFER_HOURS pass (then they come back). On yes they go to the public fund (they are what pays exits later)
and the company gets ANGEL_DOLLARS_PER_TOKEN game dollars for each. Offers are saved with the accounts.

    state.ventures["angels"] = {"a7": {"id": "a7", "company": "c1", "login": "cat", "tokens": 200, "at": time}}
"""
import time

from chatserver import (cap_table, config, fund, rooms, state, storage, textutil, ventures_rounds, ventures_store,
                        ventures_team)
from chatserver.ventures_text import money


def offers():
    return ventures_store.ensure()["angels"]


def waiting_for(co):
    return [o for o in offers().values() if o["company"] == co["id"]]


def invested(co, login):
    """🪙 this person put into this company (accepted and waiting)."""
    waiting = sum(o["tokens"] for o in waiting_for(co) if o["login"] == login)
    return co["angel_in"].get(login, 0) + waiting


def used_today(login):
    day, used = ventures_store.ensure()["angel_days"].get(login, ["", 0])
    return used if day == textutil.today() else 0


# ---------------------------------------------------------------- /invest name tokens

def offer(client, args):
    parts = args.split()
    if len(parts) == 2 and parts[0].lower() == "cancel":
        return cancel(client, parts[1])
    if len(parts) != 2 or not parts[1].isdecimal() or len(parts[1]) > 9:
        return client.say("Usage: /invest company tokens   (angel investing: 🪙 for shares of an early startup) · "
                          "/invest cancel company", "error")
    co, tokens = ventures_store.find(parts[0]), int(parts[1])
    why_not = refusal(client.key, co, parts[0], tokens)
    if why_not:
        return client.say(why_not, "error")
    dollars, bp = ventures_rounds.angel_terms(co, tokens)   # the price is fixed now: the CEO can't wait for a better one
    account = state.accounts[client.key]
    account["tokens"] -= tokens   # held until the CEO answers
    aid = f"a{ventures_store.next_id()[1:]}"
    while aid in offers():   # (never overwrite an offer that holds someone's tokens)
        aid = f"a{ventures_store.next_id()[1:]}"
    ventures_store.set_field("angels", {**offers(), aid: {"id": aid, "company": co["id"], "login": client.key,
                                                          "tokens": tokens, "dollars": dollars, "bp": bp,
                                                          "at": time.time(), "day": textutil.today()}})
    days = ventures_store.ensure()["angel_days"]
    ventures_store.set_field("angel_days", {**days, client.key: [textutil.today(), used_today(client.key) + tokens]})
    client.say(f"😇 You offered {tokens} 🪙 ({money(dollars)}) to {co['name']} for about {cap_table.percent_text(bp)}. "
               f"It's waiting for its CEO; if nobody answers in {config.ANGEL_OFFER_HOURS} h, your tokens come back.", "money")
    rooms.tell(ventures_team.ceo_of(co), f"😇 {rooms.shown(client.key)} wants to invest {tokens} 🪙 ({money(dollars)}) in "
               f"{co['name']} for about {cap_table.percent_text(bp)}. /company angel accept {rooms.nick(client.key)} "
               f"or /company angel decline {rooms.nick(client.key)}", "event")
    storage.save_data()


def refusal(login, co, name, tokens):
    if co is None or co["status"] != "alive":
        return f"❓ No company called {name}. See /ventures"
    if co["stage"] not in config.ANGEL_STAGES:
        return f"😇 Angels invest in Idea, Pre-seed and Seed companies. {co['name']} is past that."
    account = state.accounts[login]
    if time.time() - account.get("created", 0) < config.VENTURES_MIN_AGE_HOURS * 3600:
        return f"😇 Your account must be {config.VENTURES_MIN_AGE_HOURS} hours old to invest."
    if tokens < config.ANGEL_MIN:
        return f"😇 Invest at least {config.ANGEL_MIN} 🪙."
    if tokens > account["tokens"]:
        return f"💸 You have {account['tokens']} 🪙."
    left_today = config.ANGEL_MAX_PER_DAY - used_today(login)
    if tokens > left_today:
        return f"😇 You can invest at most {config.ANGEL_MAX_PER_DAY} 🪙 a day ({max(0, left_today)} left today)."
    if invested(co, login) + tokens > config.ANGEL_MAX_PER_COMPANY:
        return f"😇 At most {config.ANGEL_MAX_PER_COMPANY} 🪙 per company (you have {invested(co, login)} in {co['name']})."
    if any(o["login"] == login for o in waiting_for(co)):
        return f"⏳ Your offer to {co['name']} is still waiting for its CEO."
    bp = ventures_rounds.angel_terms(co, tokens)[1]
    if bp < 1:
        return f"😇 {tokens} 🪙 is too little to buy even 0.01% of {co['name']}."
    if co["angel_bp"] + bp > config.ANGEL_MAX_PERCENT * 100:
        return f"😇 Angels already own as much of {co['name']} as they can in this stage."
    return None


def cancel(client, name):
    """/invest cancel company: take a waiting offer back."""
    co = ventures_store.find(name)
    found = next((o for o in offers().values() if co and o["company"] == co["id"] and o["login"] == client.key), None)
    if found is None:
        return client.say(f"❓ You have no waiting offer to {name}.", "error")
    give_back(found, f"😇 You took back your offer to {co['name']}: your {found['tokens']} 🪙 came back.")
    storage.save_data()


# ---------------------------------------------------------------- the CEO answers

def list_angels(client, co, args):
    waiting = waiting_for(co)
    if not waiting:
        return client.say(f"😇 No angel offers are waiting for {co['name']}. Friends can /invest {co['name']} tokens")
    lines = [f"😇 Angel offers for {co['name']}:"]
    for o in waiting:
        dollars, bp = terms(co, o)
        lines.append(f"  {rooms.shown(o['login'])}: {o['tokens']} 🪙 = {money(dollars)} for {cap_table.percent_text(bp)}"
                     f"   /company angel accept {rooms.nick(o['login'])}")
    client.say("\n".join(lines))


def answer(client, co, args):
    """/company angel accept|decline name (the CEO)."""
    parts = args.split()
    if len(parts) != 2 or parts[0].lower() not in ("accept", "decline"):
        return client.say("Usage: /company angel accept name   or   /company angel decline name", "error")
    if ventures_team.ceo_of(co) != client.key:
        return client.say("👑 Only the CEO answers angel offers.", "error")
    login = rooms.find_account(parts[1])
    found = next((o for o in waiting_for(co) if o["login"] == login), None)
    if found is None:
        return client.say(f"❓ No angel offer from {parts[1]} is waiting.", "error")
    if parts[0].lower() == "decline":
        give_back(found, f"😇 {co['name']}'s CEO said no: your {found['tokens']} 🪙 came back.")
        client.say(f"👎 You said no to {rooms.shown(login)}'s offer.")
        return storage.save_data()
    dollars, bp = terms(co, found)
    if co["stage"] not in config.ANGEL_STAGES or co["angel_bp"] + bp > config.ANGEL_MAX_PERCENT * 100:
        give_back(found, f"😇 {co['name']} can't take more angel money now: your {found['tokens']} 🪙 came back.")
        storage.save_data()
        return client.say("😇 Angels already own as much as they can in this stage: the offer went back.", "error")
    drop(found)
    fund.collect(found["tokens"], "angel")   # 🧾 the tokens leave the player for good: the fund pays exits later
    co = ventures_team.dilute(co, cap_table.player(login), bp)
    co = ventures_store.put({**co, "cash": co["cash"] + dollars, "raised": co["raised"] + dollars,
                             "angel_bp": co["angel_bp"] + bp, "fumes": co["fumes"] and co["cash"] + dollars < 0,
                             "angel_in": {**co["angel_in"], login: co["angel_in"].get(login, 0) + found["tokens"]}})
    rooms.tell(login, f"😇 {co['name']} accepted your {found['tokens']} 🪙: you own {cap_table.percent_text(bp)} of it now.", "money")
    line = f"😇 {rooms.shown(login)} invested {money(dollars)} as an angel for {cap_table.percent_text(bp)}."
    ventures_team.tell_company(co, line)
    if client.room != co["group"]:
        client.say(line)
    storage.save_data()


def terms(co, found):
    """(dollars, bp) as promised when the offer was made (older saved offers: today's price)."""
    if "dollars" in found and "bp" in found:
        return found["dollars"], found["bp"]
    return ventures_rounds.angel_terms(co, found["tokens"])


def drop(found):
    ventures_store.set_field("angels", {k: v for k, v in offers().items() if k != found["id"]})


def give_back(found, text):
    """The held tokens go home (and back into that day's angel allowance)."""
    drop(found)
    login = found["login"]
    if login not in state.accounts:   # (accounts are never deleted, but never lose tokens silently either)
        textutil.log(f"[VENTURES] ⚠️ Angel offer {found['id']}: no account {login!r}, its tokens went to the fund.")
        fund.collect(found["tokens"], "angel")
        return
    state.accounts[login]["tokens"] += found["tokens"]
    days = ventures_store.ensure()["angel_days"]
    if found.get("day") == textutil.today() and login in days:
        day, used = days[login]
        ventures_store.set_field("angel_days", {**days, login: [day, max(0, used - found["tokens"])]})
    rooms.tell(login, text, "money")


def expire_due(now=None):
    """Called every minute: offers nobody answered (or to a company that's gone) come back."""
    now = time.time() if now is None else now
    for found in list(offers().values()):
        co = ventures_store.get(found["company"])
        if co is None or co["status"] != "alive":
            give_back(found, f"😇 The company is gone: your {found['tokens']} 🪙 came back.")
        elif now - found["at"] >= config.ANGEL_OFFER_HOURS * 3600:
            give_back(found, f"😇 {co['name']} didn't answer in {config.ANGEL_OFFER_HOURS} h: your {found['tokens']} 🪙 came back.")
        else:
            continue
        storage.save_data()
