"""
⚡ The daily actions every company has (docs/VENTURES.md, section 4), as PURE functions:
apply(company, action, args) -> (the new company, what happened), or raises ActionError(why not).
The /company commands, the website's buttons and the balance simulation's bots all use these.
"""
from chatserver import config, ventures_sim
from chatserver.ventures_store import STAFF_KINDS
from chatserver.ventures_text import money


class ActionError(Exception):
    """Why an action can't be done right now (the message is shown to the player)."""


# name: (action points, usage, what it does)
ACTIONS = {
    "build": (1, "build", "⭐ work on the product (quality up)"),
    "hire": (1, "hire engineer|sales|marketer", "👥 hire people (salaries!)"),
    "layoff": (1, "layoff engineer|sales|marketer [n]", "✂️ let people go (saves salary, costs reputation)"),
    "marketing": (1, "marketing", "📣 a campaign (hype up)"),
    "sales": (1, "sales", "🤝 a sales push (customers now)"),
    "pr": (1, "pr", "📰 press and talks (reputation up)"),
    "pivot": (3, "pivot [sector]", "🔀 start over on a new idea, once per stage"),
}


# ---------------------------------------------------------------- what each action costs ($)

def hire_count(co):
    numbers = ventures_sim.stage(co)
    return max(0, min(numbers["hire_batch"], numbers["staff_max"] - ventures_sim.staff_total(co)))


def cost(co, name, args=""):
    reach = ventures_sim.stage(co)["reach"]
    if name == "hire":
        discount = config.COO_HIRE_DISCOUNT if ventures_sim.has_role(co, "coo") else 0
        return int(config.HIRE_COST * max(1, hire_count(co)) * (1 - discount))
    if name == "layoff":
        return config.SEVERANCE * layoff_args(co, args, check=False)[1]
    if name == "marketing":
        return ventures_sim.stage(co)["marketing"]
    if name == "pr":
        return int(config.PR_COST * reach)
    return 0


def layoff_args(co, args, check=True):
    """"engineer 2" -> ("engineer", 2)."""
    parts = args.split()
    kind = parts[0].lower() if parts else ""
    number = parts[1] if len(parts) > 1 else "1"
    count = int(number) if number.isdecimal() and len(number) < 7 else 0
    have = co["staff"].get(kind, 0)
    if check and kind not in STAFF_KINDS:
        raise ActionError("Usage: /company layoff engineer|sales|marketer [n]")
    if check and not 1 <= count <= have:
        raise ActionError(f"You have {have} {kind} staff: lay off 1 to {have}." if have else f"You have no {kind} staff.")
    return kind, max(0, min(count, have))


# ---------------------------------------------------------------- the actions themselves

def do_build(co, args):
    bonus = 1 + config.CTO_BUILD_BONUS if ventures_sim.has_role(co, "cto") else 1
    amount = config.BUILD_POINTS * (1 + 0.15 * co["staff"]["engineer"] ** 0.5) * bonus
    quality = ventures_sim.grow(co["quality"], amount)
    return {"quality": quality}, f"⭐ The team shipped improvements: quality {co['quality']:.0f} → {quality:.0f}."


def do_hire(co, args):
    kind = args.split()[0].lower() if args.split() else ""
    if kind not in STAFF_KINDS:
        raise ActionError("Usage: /company hire engineer|sales|marketer")
    count = hire_count(co)
    if count == 0:
        limit = ventures_sim.stage(co)["staff_max"]
        raise ActionError(f"👥 At this stage you can have at most {limit} staff. Raise a round to grow.")
    staff = {**co["staff"], kind: co["staff"][kind] + count}
    return {"staff": staff}, f"👥 Hired {count} {kind}{'s' if count > 1 else ''} ({money(config.SALARY * count)}/day more)."


def do_layoff(co, args):
    kind, count = layoff_args(co, args)
    staff = {**co["staff"], kind: co["staff"][kind] - count}
    reputation = max(0.0, co["reputation"] - 3)
    return {"staff": staff, "reputation": reputation}, f"✂️ Let {count} {kind} staff go. Reputation {reputation:.0f}."


def do_marketing(co, args):
    bonus = 1 + config.CMO_MARKETING_BONUS if ventures_sim.has_role(co, "cmo") else 1
    hype = min(100.0, co["hype"] + config.MARKETING_POINTS * (1 - co["hype"] / 120) * bonus)
    return {"hype": hype}, f"📣 The campaign is out: hype {co['hype']:.0f} → {hype:.0f}."


def do_sales(co, args):
    bonus = 1 + config.COO_SALES_BONUS if ventures_sim.has_role(co, "coo") else 1
    sector = ventures_sim.sector(co)
    signed = sector["base_new"] * ventures_sim.stage(co)["reach"] * 0.5 * (1 + 0.1 * co["staff"]["sales"] ** 0.5) * bonus
    amount = f"{signed:.1f}" if signed < 10 else f"about {round(signed):,}"
    return ({"customers": co["customers"] + signed}, f"🤝 The sales push signed {amount} new {sector['customers']}.")


def do_pr(co, args):
    reputation = ventures_sim.grow(co["reputation"], config.PR_POINTS)
    return {"reputation": reputation}, f"📰 Good press: reputation {co['reputation']:.0f} → {reputation:.0f}."


def do_pivot(co, args):
    if co["pivoted"] == co["stage"]:
        raise ActionError("🔀 You can pivot only once per stage.")
    new_sector = args.split()[0].lower() if args.split() else co["sector"]
    if new_sector not in config.SECTORS:
        raise ActionError(f"Sectors: {', '.join(config.SECTORS)}")
    changes = {"sector": new_sector, "quality": co["quality"] * 0.5, "hype": 10.0, "customers": co["customers"] * 0.3,
               "reputation": max(0.0, co["reputation"] - 5), "pivoted": co["stage"]}
    return changes, f"🔀 Pivot! Now a {config.SECTORS[new_sector]['icon']} {config.SECTORS[new_sector]['name']} company."


HANDLERS = {"build": do_build, "hire": do_hire, "layoff": do_layoff, "marketing": do_marketing,
            "sales": do_sales, "pr": do_pr, "pivot": do_pivot}


# ---------------------------------------------------------------- doing one

def refusal(co, name, args=""):
    """Why this action can't be done now, or None (the cheap checks; the handler checks the rest)."""
    if name not in ACTIONS:
        return f"❓ Unknown action. The actions: {', '.join(ACTIONS)}"
    if co["status"] != "alive":
        return "⚰️ This company isn't alive any more."
    points = ACTIONS[name][0]
    if co["ap"] < points:
        return (f"⚡ That needs {points} action point{'s' if points > 1 else ''}, you have {co['ap']} left today. "
                f"They refill at the daily tick.")
    price = cost(co, name, args)
    if price and price > co["cash"] and name != "layoff":   # (on fumes you can still cut costs)
        return f"💸 That costs {money(price)} and the company has {money(co['cash'])} cash."
    return None


def apply(co, name, args=""):
    why_not = refusal(co, name, args)
    if why_not:
        raise ActionError(why_not)
    price = cost(co, name, args)
    changes, text = HANDLERS[name](co, args)
    new = {**co, **changes, "ap": co["ap"] - ACTIONS[name][0], "cash": co["cash"] - price, "acted": True}
    return new, text + (f" Cost: {money(price)}." if price else "")


def menu(co):
    """Every action with its cost and whether it's possible now: [{name, ap, cost, ok, why, usage, help}]."""
    rows = []
    for name, (points, usage, text) in ACTIONS.items():
        why = refusal(co, name)
        if why is None and name == "hire" and hire_count(co) == 0:
            why = "👥 staff limit for this stage"
        if why is None and name == "pivot" and co["pivoted"] == co["stage"]:
            why = "🔀 already pivoted in this stage"
        if why is None and name == "layoff" and ventures_sim.staff_total(co) == 0:
            why = "no staff to let go"
        rows.append({"name": name, "ap": points, "cost": cost(co, name), "ok": why is None, "why": why or "",
                     "usage": usage, "help": text})
    return rows
