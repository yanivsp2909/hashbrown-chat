"""
🏭 Each sector's own mechanics (docs/VENTURES.md, section 7), as PURE functions like ventures_sim.py:
🤖 AI lab (compute, training, releases, the Spud-Bench, safety and scandals), 🛡️ cybersecurity (product lines,
security, breaches), 📱 hardware (stock, batches on the way, unit cost, keynotes), 💻 SaaS (price, retention,
experiments) and 🎮 game studio (a game in development, launches, live ops).

A company keeps its sector's numbers in co["sector_state"]. The tick asks effects() for multipliers, runs day()
before money is counted, and the actions menu adds ACTIONS[sector]. world = {"tick", "events", "bench"}.
"""
import math

from chatserver import config


class SectorError(Exception):
    """Why a sector action can't be done (ventures_actions turns it into an ActionError)."""


# 🌪️ Prices that market events move right now (ventures_events.set_market keeps them up to date)
MARKET = {"compute": 1.0, "chips": 1.0}


def set_market(compute, chips):
    MARKET.update(compute=compute, chips=chips)


def compute_price():
    return int(config.COMPUTE_PRICE * MARKET["compute"])


def unit_cost(s):
    return int(s["unit_cost"] * MARKET["chips"])


def default_state(sector):
    if sector == "ai":
        return {"compute": 0, "models": [], "training": None, "safety": config.SAFETY_START}
    if sector == "cyber":
        return {"lines": {key: 0 for key in config.CYBER_LINES}, "security": config.CYBER_SECURITY_START,
                "incidents": [], "boost_until": -1}
    if sector == "hardware":
        return {"device": "phone", "stock": 0, "batches": [], "unit_cost": config.DEVICES["phone"][1], "sold": 0,
                "unmet": 0, "keynote_tick": -99, "boost": 1.0, "boost_until": -1, "gen": 1}
    if sector == "saas":
        return {"price": 1.0, "retention_until": -1}
    return {"project": {"progress": 0, "quality": 20.0, "number": 1}, "games": [], "liveops_until": -1}


def state(co):
    saved = co.get("sector_state")
    return saved if isinstance(saved, dict) and saved.get("_sector") == co["sector"] else {**default_state(co["sector"]), "_sector": co["sector"]}


def with_state(co, **changes):
    return {**co, "sector_state": {**state(co), **changes}}


def reach(co):
    return config.STAGE_NUMBERS[co["stage"]]["reach"]


# ---------------------------------------------------------------- what each sector changes in the tick

def effects(co, world):
    """Multipliers for the day: {"demand", "churn", "extra_burn"} (events from world["events"] included)."""
    s, kind = state(co), co["sector"]
    demand, churn, extra = 1.0, 1.0, 0.0
    tick = world.get("tick", 0)
    if kind == "ai":
        demand *= world.get("bench", {}).get(co["id"], 1.0)
    elif kind == "cyber":
        launched = [level for level in s["lines"].values() if level > 0]
        demand *= 1 + 0.15 * len(launched) * (sum(launched) / max(1, len(launched))) / 100 if launched else 0.5
        if s["boost_until"] >= tick:
            demand *= 1.5
    elif kind == "hardware":
        if s["boost_until"] >= tick:
            demand *= s["boost"]
        extra += s["stock"] * s["unit_cost"] * config.STOCK_COST_PERCENT / 100
    elif kind == "saas":
        churn *= s["price"] ** 0.8
        if s["retention_until"] >= tick:
            churn *= config.RETENTION_CHURN
    elif kind == "game" and s["liveops_until"] >= tick:
        churn *= 0.5
    salary = 1.0
    for event in world.get("events", []):
        if event.get("sector") in (kind, "all") or event.get("company") == co["id"]:
            demand *= event.get("demand", 1.0)
            churn *= event.get("churn", 1.0)
            salary *= event.get("salary", 1.0)
    extra += sum(co["staff"].values()) * config.SALARY * (salary - 1)   # (a talent war: everyone wants a raise)
    return {"demand": demand, "churn": churn, "extra_burn": extra}


def price_factor(co):
    return state(co)["price"] if co["sector"] == "saas" else 1.0


def hardware_revenue(co):
    s = state(co)
    price = config.DEVICES.get(s["device"], config.DEVICES["phone"])[0]
    return s["sold"] * max(0, price - s["unit_cost"])


def day(co, rng, world):
    """The sector's own day, before money is counted: (new company, report lines, news headlines)."""
    handler = {"ai": ai_day, "cyber": cyber_day, "hardware": hardware_day}.get(co["sector"])
    return handler(co, rng, world) if handler else (co, [], [])


def ai_day(co, rng, world):
    s, lines, news = state(co), [], []
    need = math.ceil(co["customers"] / 100) * config.COMPUTE_PER_100_CUSTOMERS
    compute, customers = s["compute"] - need, co["customers"]
    if compute < 0:   # 🔥 not enough GPUs: customers get errors and some leave
        compute, customers = 0, customers * 0.9
        lines.append("🔥 Out of compute: the API was down and 10% of the customers left. Buy compute!")
    training, models = s["training"], s["models"]
    if training:
        left = training["left"] - 1
        if left > 0:
            training = {**training, "left": left}
        else:
            best = max([m["score"] for m in models] + [0])
            gain = rng.uniform(3, 10) * (1 + 0.1 * co["staff"]["engineer"] ** 0.5) * co["quality"] / 100
            models = models + [{"name": f"{co['name']} {training['gen']}", "score": round(best + gain, 1),
                                "safety": s["safety"], "released": False}]
            lines.append(f"🧠 Training done: {models[-1]['name']} scores {models[-1]['score']} on Spud-Bench. Release it!")
            training = None
    return with_state({**co, "customers": customers}, compute=compute, training=training, models=models), lines, news


def cyber_day(co, rng, world):
    s = state(co)
    if co["customers"] >= 1 and rng.random() < (100 - s["security"]) / config.BREACH_DIVISOR:
        text = f"🚨 A client of {co['name']} was breached! Clients leave and trust drops."
        incidents = (s["incidents"] + [{"tick": world.get("tick", 0), "text": text}])[-5:]
        hit = {**co, "customers": co["customers"] * 0.8, "reputation": max(0.0, co["reputation"] - 20)}
        return with_state(hit, incidents=incidents), [text], [f"🚨 Breach at a client of {co['name']}"]
    return co, [], []


def hardware_day(co, rng, world):
    s, tick = state(co), world.get("tick", 0)
    arrived = sum(b["units"] for b in s["batches"] if b["arrive"] <= tick)
    batches = [b for b in s["batches"] if b["arrive"] > tick]
    stock = s["stock"] + arrived
    demand = int(co["customers"])
    sold = min(stock, demand)
    unmet = demand - sold
    lines = [f"📦 {arrived:,} units arrived."] if arrived else []
    lines.append(f"📱 Sold {sold:,} units (demand {demand:,}); {stock - sold:,} left in stock.")
    reputation = co["reputation"] - (1 if unmet > sold and demand > 0 else 0)   # sold out again: fans are angry
    return with_state({**co, "reputation": max(0.0, reputation)}, stock=stock - sold, batches=batches, sold=sold,
                      unmet=unmet), lines, []


# ---------------------------------------------------------------- the Spud-Bench (AI labs' leaderboard)

def bench(companies, tick):
    """[{name, lab, score, npc}] best first, and {company id: demand multiplier} from the rank."""
    rows = [{"name": f"{lab} {1 + tick // 7}", "lab": lab, "score": round(base + config.NPC_LAB_GROWTH * tick, 1),
             "npc": True} for lab, base in config.NPC_LABS]
    for co in companies:
        if co["sector"] != "ai" or co["status"] != "alive":
            continue
        released = [m for m in state(co)["models"] if m["released"]]
        if released:
            best = max(released, key=lambda m: m["score"])
            rows.append({"name": best["name"], "lab": co["name"], "score": best["score"], "npc": False, "id": co["id"]})
    rows.sort(key=lambda r: -r["score"])
    npc_median = sorted(base + config.NPC_LAB_GROWTH * tick for _, base in config.NPC_LABS)[len(config.NPC_LABS) // 2]
    boost = {}
    for place, row in enumerate(rows, 1):
        if not row["npc"]:
            boost[row["id"]] = 1.5 if place == 1 else 1.2 if place <= 3 else 0.8 if row["score"] < npc_median else 1.0
    return rows, boost


# ---------------------------------------------------------------- the actions

# sector: {name: (action points, usage, what it does)}
ACTIONS = {
    "ai": {"compute": (1, "compute [units]", "🖥️ buy compute (GPUs) to train and serve"),
           "train": (2, "train", "🧠 train a new model (takes 2 days)"),
           "release": (1, "release", "🚀 release your trained model on the Spud-Bench"),
           "safety": (1, "safety", "🦺 safety research (fewer scandals)")},
    "cyber": {"launch": (2, "launch agent|network|antivirus|bounty", "🧩 launch a product line"),
              "improve": (1, "improve agent|network|antivirus|bounty", "🔧 improve a product line"),
              "audit": (1, "audit", "🔍 security audit of your own systems"),
              "bounty": (1, "bounty", "🐛 run a bug bounty (security and trust)")},
    "hardware": {"manufacture": (1, "manufacture [units]", "🏭 order a batch (arrives in 2 days)"),
                 "supply": (1, "supply", "🤝 a better supplier deal (cheaper units)"),
                 "keynote": (2, "keynote", "🎤 a launch keynote: make or break"),
                 "newmodel": (3, "newmodel", "✨ start the next generation")},
    "saas": {"priceup": (1, "priceup", "💲 raise the price (more revenue, more churn)"),
             "pricedown": (1, "pricedown", "🏷️ lower the price (less churn)"),
             "retention": (1, "retention", "🫶 a retention push (less churn for 5 days)"),
             "experiment": (1, "experiment", "🧪 a growth experiment (maybe a jump)")},
    "game": {"develop": (1, "develop", "🛠️ work on the next game"),
             "playtest": (1, "playtest", "🕹️ playtest it (quality up)"),
             "launch": (2, "launch", "🚀 launch the game: hit or flop?"),
             "liveops": (1, "liveops", "📅 live events (players stay)"),
             "dlc": (1, "dlc", "🎁 sell a DLC to your players")},
}


def actions_of(co):
    return ACTIONS.get(co["sector"], {})


def units_arg(args, default, limit):
    text = args.split()[0] if args.split() else ""
    if not text:
        return default
    if not text.isdecimal() or len(text) > 6 or not 1 <= int(text) <= limit:
        raise SectorError(f"A number from 1 to {limit:,}.")
    return int(text)


def cost(co, name, args=""):
    """$ this sector action costs (0 for most)."""
    s, r = state(co), reach(co)
    if name == "compute":
        try:
            return units_arg(args, 10, 10_000) * compute_price()
        except SectorError:
            return 0
    if name == "launch" and co["sector"] == "cyber":
        return int(20_000 * r)
    if name in ("audit",):
        return int(30_000 * r)
    if name == "bounty" or (name == "dlc") or name == "retention":
        return int((20_000 if name != "retention" else 10_000) * r)
    if name == "manufacture":
        try:
            return units_arg(args, 100, int(config.BATCH_MAX * r)) * unit_cost(s)
        except SectorError:
            return 0
    if name == "keynote":
        return int(50_000 * r)
    return 0


def line_arg(args):
    key = args.split()[0].lower() if args.split() else ""
    if key not in config.CYBER_LINES:
        raise SectorError(f"Product lines: {', '.join(config.CYBER_LINES)}")
    return key


def apply(co, name, args, rng, tick):
    """Do a sector action: (changes to the company, what happened). Raises SectorError."""
    handler = HANDLERS.get((co["sector"], name))
    if handler is None:
        raise SectorError("❓ That isn't an action of this sector.")
    return handler(co, args, rng, tick)


def do_compute(co, args, rng, tick):
    units = units_arg(args, 10, 10_000)
    return with_state(co, compute=state(co)["compute"] + units), f"🖥️ Bought {units:,} compute units."


def do_train(co, args, rng, tick):
    s = state(co)
    if s["training"]:
        raise SectorError("🧠 A model is already training.")
    gen = len(s["models"]) + 1
    need = config.TRAIN_COMPUTE * gen
    if s["compute"] < need:
        raise SectorError(f"🖥️ Training model {gen} needs {need} compute units, you have {s['compute']}. Buy compute.")
    return (with_state(co, compute=s["compute"] - need, training={"gen": gen, "left": config.TRAIN_TICKS}),
            f"🧠 Training model {gen} started ({config.TRAIN_TICKS} days, {need} compute).")


def do_release(co, args, rng, tick):
    s = state(co)
    ready = [m for m in s["models"] if not m["released"]]
    if not ready:
        raise SectorError("🧠 No trained model to release. Train one first.")
    model = max(ready, key=lambda m: m["score"])
    best_before = max([m["score"] for m in s["models"] if m["released"]] + [0])
    models = [{**m, "released": True} if m is model else m for m in s["models"]]
    hype = min(100.0, co["hype"] + 3 * max(1.0, model["score"] - best_before) ** 0.5 * 4)
    changes = {"hype": hype}
    text = f"🚀 Released {model['name']} (Spud-Bench {model['score']})."
    if rng.random() < max(0.0, (60 - s["safety"]) / 100) * model["score"] / 100:
        changes = {"hype": hype, "reputation": max(0.0, co["reputation"] - 15), "customers": co["customers"] * 0.9}
        text += " 😱 SCANDAL: it said something terrible. Reputation −15, some customers left. (Safety research helps.)"
    return with_state({**co, **changes}, models=models), text


def do_safety(co, args, rng, tick):
    safety = min(100, state(co)["safety"] + 10)
    return with_state(co, safety=safety), f"🦺 Safety research: safety score {safety}/100."


def do_launch_line(co, args, rng, tick):
    key = line_arg(args)
    lines = state(co)["lines"]
    if lines[key] > 0:
        raise SectorError(f"🧩 {config.CYBER_LINES[key]} is already launched: improve it instead.")
    return with_state(co, lines={**lines, key: 20}), f"🧩 Launched {config.CYBER_LINES[key]}!"


def do_improve(co, args, rng, tick):
    key = line_arg(args)
    lines = state(co)["lines"]
    if lines[key] == 0:
        raise SectorError(f"🧩 Launch {config.CYBER_LINES[key]} first.")
    level = min(100, round(lines[key] + 10 * (1 - lines[key] / 110)))
    return with_state(co, lines={**lines, key: level}), f"🔧 {config.CYBER_LINES[key]}: level {level}."


def do_audit(co, args, rng, tick):
    security = min(100, state(co)["security"] + 15)
    return with_state(co, security=security), f"🔍 Audit done: security {security}/100."


def do_bounty(co, args, rng, tick):
    security = min(100, state(co)["security"] + 8)
    return (with_state({**co, "reputation": min(100.0, co["reputation"] + 3)}, security=security),
            f"🐛 Hackers found bugs for you: security {security}/100, reputation +3.")


def do_manufacture(co, args, rng, tick):
    s = state(co)
    units = units_arg(args, 100, int(config.BATCH_MAX * reach(co)))
    batches = s["batches"] + [{"units": units, "arrive": tick + config.MANUFACTURE_TICKS}]
    return with_state(co, batches=batches), f"🏭 Ordered {units:,} units; they arrive in {config.MANUFACTURE_TICKS} days."


def do_supply(co, args, rng, tick):
    s = state(co)
    floor = config.DEVICES.get(s["device"], config.DEVICES["phone"])[1] * 0.6
    unit_cost = max(int(floor), int(s["unit_cost"] * 0.95))
    return with_state(co, unit_cost=unit_cost), f"🤝 New supplier deal: ${unit_cost:,} a unit."


def do_keynote(co, args, rng, tick):
    s = state(co)
    if tick - s["keynote_tick"] < config.KEYNOTE_COOLDOWN:
        raise SectorError(f"🎤 One keynote every {config.KEYNOTE_COOLDOWN} days.")
    roll = co["quality"] * 0.6 + co["hype"] * 0.4 + rng.uniform(-20, 20)
    if roll >= 70:
        changes, boost, text = {"hype": min(100.0, co["hype"] + 30)}, 2.0, "🎤 TRIUMPH! The crowd went wild: demand doubles for 3 days."
    elif roll >= 40:
        changes, boost, text = {}, 1.3, "🎤 A solid keynote: demand +30% for 3 days."
    else:
        changes = {"hype": max(0.0, co["hype"] - 20), "reputation": max(0.0, co["reputation"] - 10)}
        boost, text = 1.0, "🎤 The keynote flopped: the demo crashed on stage. Hype −20, reputation −10."
    return (with_state({**co, **changes}, keynote_tick=tick, boost=boost, boost_until=tick + 3), text)


def do_newmodel(co, args, rng, tick):
    s = state(co)
    return (with_state({**co, "quality": co["quality"] * 0.6 + 15}, gen=s["gen"] + 1),
            f"✨ Generation {s['gen'] + 1} is in design: quality resets a bit, but it's new.")


def do_price(co, up):
    s = state(co)
    price = min(2.0, s["price"] * config.SAAS_PRICE_STEP) if up else max(0.5, s["price"] / config.SAAS_PRICE_STEP)
    return with_state(co, price=round(price, 3)), f"💲 Price is now {price:.0%} of the usual."


def do_retention(co, args, rng, tick):
    return with_state(co, retention_until=tick + config.RETENTION_TICKS), "🫶 Retention push: churn is lower for 5 days."


def do_experiment(co, args, rng, tick):
    if rng.random() < 0.5:
        gain = rng.uniform(0.05, 0.15)
        return {**co, "customers": co["customers"] * (1 + gain)}, f"🧪 The experiment worked: users +{gain:.0%}!"
    return co, "🧪 The experiment didn't move anything. We learned something, at least."


def do_develop(co, args, rng, tick):
    project = state(co)["project"]
    progress = min(100, project["progress"] + round(rng.uniform(10, 20) * (1 + 0.1 * co["staff"]["engineer"])))
    quality = min(100.0, project["quality"] + 3)
    return with_state(co, project={**project, "progress": progress, "quality": quality}), f"🛠️ Game {project['number']}: {progress}% done."


def do_playtest(co, args, rng, tick):
    project = state(co)["project"]
    quality = min(100.0, project["quality"] + 6)
    hint = "players loved it" if quality >= 70 else "mixed feelings" if quality >= 45 else "players were bored"
    return with_state(co, project={**project, "quality": quality}), f"🕹️ Playtest: {hint} (quality {quality:.0f})."


def do_launch_game(co, args, rng, tick):
    s = state(co)
    project = s["project"]
    if project["progress"] < 100:
        raise SectorError(f"🛠️ The game is {project['progress']}% done. Develop it to 100% first.")
    roll = project["quality"] * 0.5 + co["hype"] * 0.4 + rng.uniform(-25, 25)
    base = config.SECTORS["game"]["base_new"] * reach(co)
    players, verdict = (base * 5, "🎉 A HIT!") if roll >= 75 else (base * 1.5, "🙂 Fine.") if roll >= 40 else (base * 0.3, "💀 A flop.")
    game = {"name": f"{co['name']} {project['number']}", "players": int(players), "review": int(min(100, roll)), "hit": roll >= 75}
    sequel = 10 if roll >= 75 else 0
    new_project = {"progress": 0, "quality": 20.0 + sequel, "number": project["number"] + 1}
    cash = co["cash"] + int(players * config.GAME_SALE_PRICE)
    changes = {"customers": co["customers"] + players, "cash": cash}
    return (with_state({**co, **changes}, games=(s["games"] + [game])[-6:], project=new_project),
            f"🚀 {game['name']} launched: {verdict} {int(players):,} new players (${int(players * config.GAME_SALE_PRICE):,} in sales).")


def do_liveops(co, args, rng, tick):
    return (with_state({**co, "customers": co["customers"] * 1.05}, liveops_until=tick + config.LIVEOPS_TICKS),
            "📅 Live events: players stay longer for 3 days (+5% now).")


def do_dlc(co, args, rng, tick):
    earned = int(co["customers"] * 0.5)
    return {**co, "cash": co["cash"] + earned}, f"🎁 The DLC sold: +${earned:,}."


HANDLERS = {
    ("ai", "compute"): do_compute, ("ai", "train"): do_train, ("ai", "release"): do_release, ("ai", "safety"): do_safety,
    ("cyber", "launch"): do_launch_line, ("cyber", "improve"): do_improve, ("cyber", "audit"): do_audit,
    ("cyber", "bounty"): do_bounty,
    ("hardware", "manufacture"): do_manufacture, ("hardware", "supply"): do_supply, ("hardware", "keynote"): do_keynote,
    ("hardware", "newmodel"): do_newmodel,
    ("saas", "priceup"): lambda co, a, r, t: do_price(co, True), ("saas", "pricedown"): lambda co, a, r, t: do_price(co, False),
    ("saas", "retention"): do_retention, ("saas", "experiment"): do_experiment,
    ("game", "develop"): do_develop, ("game", "playtest"): do_playtest, ("game", "launch"): do_launch_game,
    ("game", "liveops"): do_liveops, ("game", "dlc"): do_dlc,
}


# ---------------------------------------------------------------- what the HQ's sector panel shows

def panel(co, world):
    s = state(co)
    data = {k: v for k, v in s.items() if not k.startswith("_")}
    if co["sector"] == "ai":
        rows, _ = bench(world.get("companies", []), world.get("tick", 0))
        data = {**data, "bench": rows[:8], "compute_need": math.ceil(co["customers"] / 100) * config.COMPUTE_PER_100_CUSTOMERS,
                "train_cost": config.TRAIN_COMPUTE * (len(s["models"]) + 1), "compute_price": compute_price()}
    elif co["sector"] == "cyber":
        data = {**data, "names": config.CYBER_LINES}
    elif co["sector"] == "hardware":
        data = {**data, "price": config.DEVICES.get(s["device"], config.DEVICES["phone"])[0], "unit_cost_now": unit_cost(s),
                "keynote_ready": world.get("tick", 0) - s["keynote_tick"] >= config.KEYNOTE_COOLDOWN}
    return {"sector": co["sector"], **data}
