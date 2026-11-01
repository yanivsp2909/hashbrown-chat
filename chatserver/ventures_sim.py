"""
🏢 The game's numbers and the daily tick, as PURE functions: a company dict goes in, a NEW company dict comes out.
No time, no files, no state: the server's tick (ventures_tick.py), the tests and the balance simulation
(ventures_balance.py) all call the same functions. The formulas are in docs/VENTURES.md, section 5.
"""
from chatserver import config, ventures_text


def sector(co):
    return config.SECTORS[co["sector"]]


def stage(co):
    return config.STAGE_NUMBERS[co["stage"]]


def has_role(co, role):
    return role in co["roles"].values()


def staff_total(co):
    return sum(co["staff"].values())


def grow(value, amount, ceiling=110):
    """Add `amount`, slower near the top (the last points are the hardest), kept in 0-100."""
    return max(0.0, min(100.0, value + amount * (1 - value / ceiling)))


# ---------------------------------------------------------------- money

def revenue(co):
    return co["customers"] * sector(co)["price"]


def burn(co, players):
    """$ a day: salaries, the players' pay, the office and the cost of revenue (a CFO cuts it)."""
    total = (staff_total(co) * config.SALARY + players * config.FOUNDER_PAY + stage(co)["office"]
             + revenue(co) * sector(co)["cost_of_revenue"])
    return total * (1 - config.CFO_BURN_CUT) if has_role(co, "cfo") else total


def runway(co, players):
    """Days of cash left at today's speed, or None when the company earns more than it spends."""
    loss = burn(co, players) - revenue(co)
    if loss <= 0:
        return None
    return max(0, int(co["cash"] // loss))


def attract(co):
    """How much customers want it: quality, hype and reputation together (1.0 is about average)."""
    return ((co["quality"] / 50) ** 1.2 * (0.5 + co["hype"] / 100) * (0.6 + co["reputation"] / 125))


def valuation(co, mood=1.0):
    """The paper value: yearly revenue x the sector's multiple, better with quality, hype and reputation, and
    never much below the last round (investors don't forget so fast)."""
    mark = (revenue(co) * 12 * sector(co)["multiple"] * (0.5 + co["quality"] / 100)
            * (0.7 + co["hype"] / 200) * (0.7 + co["reputation"] / 170) * mood)
    return max(mark, co["last_post"] * 0.8)


# ---------------------------------------------------------------- milestones

def milestones(co, players=1):
    """What the next round needs: [{"what", "need", "have", "ok"}] (empty for a public company)."""
    if co["stage"] not in config.ROUNDS:
        return []
    need = config.ROUNDS[co["stage"]]
    rows = []
    if need["mrr"]:
        rows.append(row("MRR", need["mrr"], revenue(co)))
    rows.append(row("quality", need["quality"], co["quality"]))
    if need["reputation"]:
        rows.append(row("reputation", need["reputation"], co["reputation"]))
    rows.append(row("ticks", config.ROUND_MIN_TICKS, co["stage_ticks"]))
    if co["stage"] == "c":   # 🔔 the IPO also needs a big valuation and nearly no losses
        rows.append(row("valuation", need["floor"], valuation(co)))
        rows.append(row("profit", config.IPO_PROFIT_PERCENT, revenue(co) / max(1.0, burn(co, players)) * 100))
    return rows


def row(what, need, have):
    return {"what": what, "need": need, "have": have, "ok": have >= need}


def ready(co, players=1):
    rows = milestones(co, players)
    return bool(rows) and all(r["ok"] for r in rows)


# ---------------------------------------------------------------- the daily tick

def next_day(co, rng, players, mood=1.0):
    """One tick for one live company. Returns (the new company, the report lines)."""
    idle = 0 if co["acted"] else co["idle"] + 1
    quality, hype, reputation = product_and_buzz(co, idle)
    luck_lines, customers, hype, reputation = luck(co, rng, co["customers"], hype, reputation)
    moved = {**co, "quality": quality, "hype": hype, "reputation": reputation, "customers": customers}
    new = customers_arrive(moved, rng)
    lost = customers * sector(co)["churn"] * (1.4 - quality / 100) * (2 if idle >= config.IDLE_TICKS else 1)
    moved = {**moved, "customers": max(0.0, customers + new - lost)}
    earned, spent = revenue(moved), burn(moved, players)
    cash = int(round(co["cash"] + earned - spent))
    value = valuation({**moved, "cash": cash}, mood)
    result = {**moved, "cash": cash, "revenue": int(earned), "burn": int(spent), "valuation": int(value),
              "peak": int(max(co["peak"], value)), "age": co["age"] + 1, "stage_ticks": co["stage_ticks"] + 1,
              "idle": idle, "acted": False}
    result, death_lines = check_cash(result, players)
    days_left = runway(result, players)
    numbers = {"tick": co["age"] + 1, "revenue": earned, "old_revenue": revenue(co), "burn": spent,
               "runway": days_left, "new": new, "lost": lost}
    warning = []
    if result["status"] == "alive" and not result["fumes"] and days_left is not None \
            and days_left < config.RUNWAY_WARNING_TICKS:
        warning = [f"⏳ Only {days_left} days of cash left at this speed: raise money or cut costs."]
    return result, ventures_text.report_lines(co, result, numbers) + luck_lines + warning + death_lines


def product_and_buzz(co, idle):
    """Engineers polish the product; hype fades (marketers and a CMO keep it up); idle companies fade fast."""
    staff = co["staff"]
    quality = grow(co["quality"], config.ENGINEER_POLISH * staff["engineer"] ** 0.7)
    keep = config.CMO_HYPE_KEEP if has_role(co, "cmo") else config.HYPE_KEEP
    hype = co["hype"] * keep + staff["marketer"] ** 0.6 * (1 - co["hype"] / 120)
    reputation = co["reputation"]
    if idle >= config.IDLE_TICKS:   # 💤 investors smell a zombie
        hype, reputation = hype * 0.5, reputation - 2
    return quality, max(0.0, min(100.0, hype)), max(0.0, min(100.0, reputation))


def luck(co, rng, customers, hype, reputation):
    """🎲 Sometimes a setback, sometimes good luck (the events of Phase 3 will replace this)."""
    lines = []
    if rng.random() < config.LUCK_CHANCE:
        customers = customers * (1 - rng.uniform(0.10, 0.25))
        reputation = max(0.0, reputation - rng.uniform(3, 10))
        lines.append("🌧️ A bad day: a bug hit the users and some of them left.")
    if rng.random() < config.LUCK_CHANCE:
        hype = min(100.0, hype + rng.uniform(5, 20))
        reputation = min(100.0, reputation + rng.uniform(2, 6))
        lines.append("🍀 Good luck: someone famous posted about you.")
    return lines, customers, hype, reputation


def customers_arrive(co, rng):
    """New customers today: the sector's base x the stage's reach x sales staff x how attractive it is."""
    reach = stage(co)["reach"] * (1 + 0.08 * co["staff"]["sales"] ** 0.8)
    return sector(co)["base_new"] * reach * attract(co) * rng.uniform(0.7, 1.3)


def check_cash(co, players):
    """Below zero: one tick "on fumes" to save it, then it dies."""
    if co["cash"] >= 0:
        return {**co, "fumes": False}, []
    if not co["fumes"]:
        return {**co, "fumes": True}, ["🚨 Out of cash: the company is on fumes! Raise money or cut costs "
                                      "before the next tick, or it dies."]
    cause = death_cause(co, players)
    return {**co, "status": "dead", "cause": cause}, [f"⚰️ {co['name']} ran out of money and died: {cause}."]


def death_cause(co, players):
    """A short story of why it died, from the numbers."""
    people = staff_total(co)
    if co["idle"] >= config.IDLE_TICKS:
        return "the founders stopped showing up"
    if co["customers"] < 1:
        return "it never found customers"
    if co["quality"] < 20:
        return "the product never got good enough"
    if people >= 10 and revenue(co) < burn(co, players) * 0.3:
        return f"it ran out of runway with {people} people on the payroll"
    return "it spent faster than it earned"
