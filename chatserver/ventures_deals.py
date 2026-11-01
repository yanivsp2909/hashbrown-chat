"""
🏁 Competition and the endgame (docs/VENTURES.md, section 9): market share in each sector, partnerships, poaching
staff, acquisitions (an offer the other CEO accepts or declines), and the IPO onto the stock market as "#name".
Money that turns into 🪙 always goes through ventures_exits (tax, cap, the fund first, the season's mint cap).
"""
import random
import time
from collections import deque

from chatserver import (config, fund, market, rooms, state, storage, ventures_actions, ventures_exits, ventures_news,
                        ventures_sim, ventures_store, ventures_team)
from chatserver.ventures_text import money, sector_title


# ---------------------------------------------------------------- market share and crowding

def crowd(companies):
    """{company id: demand factor}: every strong rival in your sector (at least half as attractive) takes a bit."""
    factors = {}
    for co in companies:
        mine = ventures_sim.attract(co)
        rivals = sum(1 for other in companies if other["id"] != co["id"] and other["sector"] == co["sector"]
                     and ventures_sim.attract(other) >= mine / 2)
        factors[co["id"]] = 1 / (1 + config.CROWD_EFFECT * rivals)
    return factors


def shares(companies):
    """{sector: [{"id", "name", "share" (0-1), "customers"}]} with the incumbents' slice in the total."""
    board = {}
    for sector in config.SECTORS:
        players = [co for co in companies if co["sector"] == sector]
        total = sum(co["customers"] for co in players) + config.INCUMBENTS[sector]
        board[sector] = sorted([{"id": co["id"], "name": co["name"], "customers": co["customers"],
                                 "share": co["customers"] / total} for co in players], key=lambda r: -r["share"])
    return board


def demand_bonus(co, tick):
    """Partnerships and bought companies bring more new customers."""
    partner = co.get("partner") or {}
    bonus = config.PARTNER_BONUS if partner.get("until", -1) >= tick else 0.0
    return 1 + bonus + co.get("synergy", 0.0)


# ---------------------------------------------------------------- helpers

def target(client, name):
    co = ventures_store.find(name) if name else None
    if co is None or co["status"] != "alive":
        client.say(f"❓ No live company called {name or '...'}. See /ventures", "error")
        return None
    return co


def ceo_only(client, co):
    if ventures_team.ceo_of(co) != client.key:
        client.say("👑 Only the CEO makes deals.", "error")
        return False
    return True


def tell_ceo(co, text, **extra):
    rooms.tell(ventures_team.ceo_of(co), text, "event", **extra)


# ---------------------------------------------------------------- partnerships

def partner(client, co, args):
    """/company partner <other>  ·  /company partner accept <other>."""
    parts = args.split()
    if not parts:
        return client.say("Usage: /company partner company   ·   /company partner accept company", "error")
    if not ceo_only(client, co):
        return None
    accepting = parts[0].lower() == "accept" and len(parts) > 1
    other = target(client, parts[1] if accepting else parts[0])
    if other is None:
        return None
    tick = ventures_store.ensure()["tick"]
    why_not = partner_refusal(co, other, tick)
    if why_not:
        return client.say(why_not, "error")
    offers = ventures_store.ensure()["partner_offers"]
    if accepting:
        offer = offers.get(co["id"])
        if not offer or offer.get("from") != other["id"]:
            return client.say(f"❓ {other['name']} didn't offer you a partnership.", "error")
        until = tick + config.PARTNER_TICKS
        ventures_store.put({**co, "partner": {"with": other["id"], "until": until}})
        ventures_store.put({**ventures_store.get(other["id"]), "partner": {"with": co["id"], "until": until}})
        ventures_store.set_field("partner_offers", {k: v for k, v in offers.items() if k != co["id"]})
        ventures_news.add("partner", f"🤝 {co['name']} and {other['name']} are partners for {config.PARTNER_TICKS} days", co)
        client.say(f"🤝 Partners with {other['name']}: +{int(config.PARTNER_BONUS * 100)}% new customers for both.")
        tell_ceo(other, f"🤝 {co['name']} accepted: you're partners for {config.PARTNER_TICKS} days.")
    else:
        ventures_store.set_field("partner_offers", {**offers, other["id"]: {"from": co["id"], "at": time.time()}})
        client.say(f"🤝 Partnership offered to {other['name']}. Their CEO answers with /company partner accept {co['name']}")
        tell_ceo(other, f"🤝 {co['name']} ({sector_title(co['sector'])}) offers a partnership: +"
                        f"{int(config.PARTNER_BONUS * 100)}% new customers for both for {config.PARTNER_TICKS} days. "
                        f"/company partner accept {co['name']}", partner_offer={"company": co["id"], "name": co["name"]})
    storage.save_data()
    return None


def partner_refusal(co, other, tick):
    if other["id"] == co["id"]:
        return "🙃 That's your own company."
    if other["sector"] == co["sector"]:
        return "🤝 Partners come from another sector (in yours, you're rivals)."
    for c in (co, other):
        if (c.get("partner") or {}).get("until", -1) >= tick:
            return f"🤝 {c['name']} already has a partner."
    return None


# ---------------------------------------------------------------- poaching

def poach(client, co, args):
    """/company poach <other> <engineer|sales|marketer>: try to hire their people away."""
    parts = args.split()
    if len(parts) != 2 or parts[1].lower() not in ventures_store.STAFF_KINDS:
        return client.say("Usage: /company poach company engineer|sales|marketer", "error")
    other = target(client, parts[0])
    if other is None or not ceo_only(client, co):
        return None
    kind, tick = parts[1].lower(), ventures_store.ensure()["tick"]
    price = int(config.POACH_COST * ventures_sim.stage(co)["reach"])
    count = min(ventures_sim.stage(co)["hire_batch"], other["staff"][kind], ventures_actions.hire_count(co) or 0)
    why_not = poach_refusal(co, other, kind, count, price, tick)
    if why_not:
        return client.say(why_not, "error")
    poached = ventures_store.ensure()["poached"]
    day, times = poached.get(other["id"], {}).get("tick"), poached.get(other["id"], {}).get("n", 0)
    ventures_store.set_field("poached", {**poached, other["id"]: {"tick": tick, "n": (times if day == tick else 0) + 1}})
    gap = (co["valuation"] - other["valuation"]) / max(1, co["valuation"], other["valuation"])
    chance = max(0.1, min(0.7, 0.3 + 0.3 * gap))
    co = ventures_store.put({**co, "ap": co["ap"] - config.POACH_AP, "cash": co["cash"] - price, "acted": True})
    if random.random() >= chance:
        storage.save_data()
        return ventures_team.tell_both(client, co, f"🎣 {other['name']}'s {kind} staff said no ({int(chance * 100)}% chance). −{money(price)}")
    ventures_store.put({**co, "staff": {**co["staff"], kind: co["staff"][kind] + count}})
    ventures_store.put({**other, "staff": {**other["staff"], kind: other["staff"][kind] - count}})
    ventures_team.tell_both(client, ventures_store.get(co["id"]), f"🎣 Poached {count} {kind} staff from {other['name']}! −{money(price)}")
    tell_ceo(other, f"🎣 {co['name']} poached {count} of your {kind} staff.")
    storage.save_data()
    return None


def poach_refusal(co, other, kind, count, price, tick):
    if other["id"] == co["id"]:
        return "🙃 That's your own company."
    if count <= 0:
        return f"🎣 Nobody to poach: {other['name']} has no {kind} staff, or you're at your staff limit."
    if co["ap"] < config.POACH_AP:
        return f"⚡ Poaching needs {config.POACH_AP} action points, you have {co['ap']}."
    if price > co["cash"]:
        return f"💸 Poaching costs {money(price)}, the company has {money(co['cash'])}."
    record = ventures_store.ensure()["poached"].get(other["id"], {})
    if record.get("tick") == tick and record.get("n", 0) >= config.POACH_PER_DAY:
        return f"🎣 {other['name']} was poached {config.POACH_PER_DAY} times today already."
    return None


# ---------------------------------------------------------------- acquisitions

def self_dealing(buyer, seller):
    """Someone on both sides (a member of both, or more than SELF_DEAL_PERCENT of both)?"""
    both = set(ventures_store.members(buyer)) & set(ventures_store.members(seller))
    big = {h for h, bp in buyer["cap"].items() if h.startswith("p:") and bp > config.SELF_DEAL_PERCENT * 100} & \
          {h for h, bp in seller["cap"].items() if h.startswith("p:") and bp > config.SELF_DEAL_PERCENT * 100}
    return bool(both or big)


def acquire(client, co, args):
    """/company acquire <target> <amount>."""
    from chatserver.ventures_rounds import parse_money
    parts = args.split()
    amount = parse_money(parts[1]) if len(parts) == 2 else None
    if amount is None:
        return client.say("Usage: /company acquire company amount   (like /company acquire Spudly 5M)", "error")
    other = target(client, parts[0])
    if other is None or not ceo_only(client, co):
        return None
    why_not = acquire_refusal(co, other, amount)
    if why_not:
        return client.say(why_not, "error")
    offer = {"id": f"q{int(time.time() * 1000) % 10**9}", "from": co["id"], "amount": amount, "at": time.time()}
    ventures_store.set_field("acquisitions", {**ventures_store.ensure()["acquisitions"], other["id"]: offer})
    client.say(f"🤝 Offered {money(amount)} for {other['name']}. Their CEO has {config.ACQUIRE_OFFER_HOURS} h to answer.")
    card = {"id": offer["id"], "buyer": co["name"], "target": other["name"], "amount": amount,
            "expires": int(offer["at"] + config.ACQUIRE_OFFER_HOURS * 3600)}
    for login in ventures_store.members(other):
        rooms.tell(login, f"🤝 {co['name']} wants to buy {other['name']} for {money(amount)} (valued {money(other['valuation'])}). "
                          f"Holders are paid out. CEO: /company sell accept or /company sell decline", "event", acquisition=card)
    storage.save_data()
    return None


def acquire_refusal(co, other, amount):
    if other["id"] == co["id"]:
        return "🙃 You can't buy your own company."
    if config.STAGES.index(co["stage"]) < config.STAGES.index(config.ACQUIRE_MIN_STAGE):
        return f"🤝 Companies buy others from {config.STAGE_NAMES[config.ACQUIRE_MIN_STAGE]} on."
    if other["stage"] == "public":
        return "🔔 A public company can't be bought here (its shares trade on the market)."
    if self_dealing(co, other):
        return "🚫 Someone is on both sides of this deal. Not allowed."
    minimum = int(other["valuation"] * config.ACQUIRE_MIN_PERCENT / 100)
    if amount < minimum:
        return f"🤝 At least {config.ACQUIRE_MIN_PERCENT}% of its valuation: {money(minimum)}."
    if amount > co["cash"]:
        return f"💸 {co['name']} has {money(co['cash'])} cash."
    return None


def sell(client, co, args):
    """/company sell accept|decline: the CEO answers an offer to buy their company."""
    answer = args.strip().lower()
    offer = ventures_store.ensure()["acquisitions"].get(co["id"])
    if answer not in ("accept", "decline") or not offer:
        return client.say("🤝 No offer to buy your company is waiting." if not offer else
                          "Usage: /company sell accept   or   /company sell decline", "error")
    if not ceo_only(client, co):
        return None
    drop_offer(co["id"])
    buyer = ventures_store.get(offer["from"])
    if answer == "decline":
        if buyer:
            tell_ceo(buyer, f"🤝 {co['name']} said no to your offer.")
        storage.save_data()
        return client.say(f"👎 You turned down {buyer['name'] if buyer else 'the'} offer.")
    if not buyer or buyer["status"] != "alive" or buyer["cash"] < offer["amount"] or self_dealing(buyer, co):
        return client.say("🤝 The buyer can't pay any more (or the deal isn't allowed now): the offer is gone.", "error")
    merge(buyer, co, offer["amount"])
    return None


def merge(buyer, co, amount):
    """The buyer pays, the holders get their exit, the customers and staff move, the bought company ends happily."""
    same = buyer["sector"] == co["sector"]
    staff = dict(buyer["staff"])
    room = ventures_sim.stage(buyer)["staff_max"] - ventures_sim.staff_total(buyer)
    for kind in ventures_store.STAFF_KINDS:
        moved = min(room, co["staff"][kind]) if same else 0
        staff[kind] += moved
        room -= moved
    changes = {"cash": buyer["cash"] - amount, "staff": staff,
               "customers": buyer["customers"] + (co["customers"] * config.ACQUIRE_KEEP_CUSTOMERS if same else 0),
               "synergy": buyer.get("synergy", 0.0) + (0 if same else config.PARTNER_BONUS)}
    ventures_store.put({**buyer, **changes})
    ventures_exits.pay_exit(co, amount, "acquisition")
    co = ventures_store.put({**co, "status": "acquired", "cause": f"bought by {buyer['name']} for {money(amount)}"})
    ventures_team.bury(co, "was acquired")
    ventures_news.add("acquisition", f"🤝 {buyer['name']} bought {co['name']} for {money(amount)}!", buyer, big=True)
    storage.save_data()


def drop_offer(cid):
    ventures_store.set_field("acquisitions", {k: v for k, v in ventures_store.ensure()["acquisitions"].items() if k != cid})


def expire_due(now=None):
    """Called every minute: old offers go."""
    now = time.time() if now is None else now
    for cid, offer in list(ventures_store.ensure()["acquisitions"].items()):
        if now - offer["at"] >= config.ACQUIRE_OFFER_HOURS * 3600 or not ventures_store.get(cid):
            drop_offer(cid)


# ---------------------------------------------------------------- the IPO

def ipo(client, co, args):
    """/company ipo: Series C with the IPO milestones -> listed on the market, holders get their exit."""
    if not ceo_only(client, co):
        return None
    players = len(ventures_store.members(co))
    if co["stage"] != "c" or not ventures_sim.ready(co, players):
        return client.say("🔔 The IPO needs Series C and its milestones (see /company).", "error")
    value = int(ventures_sim.valuation(co) * random.uniform(0.9, 1.2))   # 🎉 the IPO pop
    raised = value * config.IPO_NEW_SHARES_PERCENT // 100
    symbol = "#" + co["group"]
    price = max(config.STOCK_MIN_PRICE, value // config.IPO_DOLLARS_PER_TOKEN_PRICE)
    holders_before = {**co, "cap": co["cap"]}
    co = ventures_team.dilute(co, "public", config.IPO_NEW_SHARES_PERCENT * 100)
    co = ventures_store.put({**co, "stage": "public", "stage_ticks": 0, "cash": co["cash"] + raised,
                             "raised": co["raised"] + raised, "valuation": value, "peak": max(co["peak"], value),
                             "ipo": {"symbol": symbol, "value": value, "tick": ventures_store.ensure()["tick"], "price": price}})
    market.ensure()
    state.stocks[symbol] = {"price": price, "open": price, "history": deque(maxlen=config.STOCK_HISTORY_POINTS)}
    state.stocks[symbol]["history"].append((int(time.time()), price))
    ventures_exits.pay_exit(holders_before, value, "IPO")
    ventures_news.add("ipo", f"🔔 {co['name']} is PUBLIC! Valued {money(value)}, trading as {symbol.upper()} at {price} 🪙", co,
                      big=True)
    ventures_team.send_event(co, "ipo", f"🔔 {co['name']} is public: {money(value)}!")
    storage.save_data()
    return None


def stock_tick():
    """Every market tick: a public company's price walks toward its valuation (like group stocks follow theirs)."""
    now = int(time.time())
    for co in ventures_store.alive():
        symbol = (co.get("ipo") or {}).get("symbol")
        stock = state.stocks.get(symbol) if symbol else None
        if not stock:
            continue
        goal = max(config.STOCK_MIN_PRICE, co["valuation"] // config.IPO_DOLLARS_PER_TOKEN_PRICE)
        gap = goal - stock["price"]
        step = gap * config.IPO_FOLLOW_PERCENT // 100 or (1 if gap > 0 else -1 if gap < 0 else 0)
        stock["price"] = max(config.STOCK_MIN_PRICE, stock["price"] + step)
        stock["history"].append((now, stock["price"]))


def delist(co, why):
    """A public company died or the season ended: the stock goes, shareholders get the last price from the fund
    only (whatever the fund can't pay waits in the exit queue)."""
    symbol = (co.get("ipo") or {}).get("symbol")
    stock = state.stocks.pop(symbol, None) if symbol else None
    if not stock:
        return
    for login, account in state.accounts.items():
        shares = account.get("portfolio", {}).get(symbol, 0)
        if not shares:
            continue
        account["portfolio"] = {k: v for k, v in account["portfolio"].items() if k != symbol}
        account["spent"] = {k: v for k, v in account.get("spent", {}).items() if k != symbol}
        owed = shares * stock["price"]
        paid = fund.pay_from_fund_only(login, owed)
        if owed > paid:
            queue = ventures_store.ensure().get("exit_queue", [])
            ventures_store.set_field("exit_queue", queue + [{"login": login, "tokens": owed - paid, "why": f"{symbol} delisted",
                                                             "at": time.time()}])
        rooms.tell(login, f"🔕 {symbol.upper()} was delisted ({why}): your {shares} shares were paid at {stock['price']} 🪙 each.",
                   "money")
    ventures_store.put({**co, "ipo": {**co["ipo"], "delisted": True}})
