"""
💰 Funding rounds: the investors, their score and fair offer, clamping what the AI suggests, term sheets
(accept / decline / counter once / expire) and the bridge round. docs/VENTURES.md, section 6.
The math functions are pure (a company in, numbers or a new company out); the rest changes state.ventures.
"""
import math
import re
import time

from chatserver import (cap_table, config, rooms, state, storage, ventures_log, ventures_sim, ventures_store,
                        ventures_team, ventures_tick)
from chatserver.ventures_text import money, stage_name

INVESTORS = {
    "dana": {"name": "Dana Goodwin", "firm": "angel investor", "emoji": "😇", "stages": ["idea"], "sectors": None,
             "style": "warm and curious; asks about the founders and why they care", "factor": 1.05, "flex": 0.20,
             "questions": ["Why are you the right people to build this?", "Who is your first real customer?",
                           "What happens if a big company copies you?"]},
    "avi": {"name": "Prof. Avi Lerner", "firm": "deep-tech angel", "emoji": "🦉", "stages": ["idea", "preseed"],
            "sectors": ["ai", "cyber", "hardware"], "style": "technical and precise; asks how it really works",
            "factor": 1.0, "flex": 0.15,
            "questions": ["How does it work under the hood?", "What is the hardest technical risk?",
                          "How much does each customer cost you to serve?"]},
    "maya": {"name": "Maya Stone", "firm": "Granite Ventures", "emoji": "🦈", "stages": ["preseed", "seed", "a"],
             "sectors": None, "style": "a tough partner who loves numbers: churn, unit economics, growth",
             "factor": 0.90, "flex": 0.10,
             "questions": ["What is your churn, and why will it go down?", "How much does a customer cost to win?",
                           "What would make this company fail?"]},
    "leo": {"name": "Leo Hart", "firm": "Rocket Capital", "emoji": "🚀", "stages": ["seed", "a"], "sectors": None,
            "style": "excited by hype and huge visions; afraid of missing out", "factor": 1.0, "flex": 0.25,
            "questions": ["How big can this get in five years?", "Why is everyone going to talk about you?",
                          "Who else is trying to invest in you?"]},
    "helen": {"name": "Helen Ward", "firm": "Ironclad Growth", "emoji": "🏛️", "stages": ["a", "b"], "sectors": None,
              "style": "a calm growth investor; margins and the path to profit", "factor": 0.95, "flex": 0.10,
              "questions": ["When do you become profitable?", "What happens to your margins at ten times the size?",
                            "Which market do you open next?"]},
    "kenji": {"name": "Kenji Sato", "firm": "Dragon Crossover Fund", "emoji": "🐉", "stages": ["b"], "sectors": None,
              "style": "a big crossover fund preparing companies for the IPO; risks and competition",
              "factor": 1.0, "flex": 0.15,
              "questions": ["Are you ready to be a public company?", "Who is your strongest competitor?",
                            "What is the biggest risk in your numbers?"]},
    "bridge": {"name": "Bridge Capital", "firm": "bridge lender", "emoji": "🌉", "stages": [], "sectors": None,
               "style": "", "factor": 1.0, "flex": 0.0, "questions": []},
}


def investor_title(investor_id):
    info = INVESTORS.get(investor_id)
    return f"{info['emoji']} {info['name']} ({info['firm']})" if info else f"💼 {investor_id}"


def eligible(co):
    """The investors who do this company's next round."""
    return [iid for iid, info in INVESTORS.items() if co["stage"] in info["stages"]
            and (info["sectors"] is None or co["sector"] in info["sectors"])]


def factor(co, investor_id):
    info = INVESTORS[investor_id]
    if investor_id == "leo":   # 🚀 pays for hype
        return 1.10 if co["hype"] > 60 else 0.95
    return info["factor"]


# ---------------------------------------------------------------- the score and the fair offer

def score(co, rating, players=1):
    """0..1: how good this company looks for its next round (numbers 90%, the pitch 10%)."""
    need = config.ROUNDS[co["stage"]]
    if need["mrr"]:
        growth = min(1.0, max(0.0, ventures_sim.revenue(co) / need["mrr"] - 1))
    else:
        growth = min(1.0, max(0.0, (co["quality"] - need["quality"]) / 30))
    quality = max(0.0, (co["quality"] - need["quality"]) / (100 - need["quality"]))
    total = (0.35 * growth + 0.25 * min(1.0, quality) + 0.15 * co["hype"] / 100 + 0.15 * co["reputation"] / 100
             + 0.10 * max(0, min(10, rating)) / 10)
    return max(0.0, min(1.0, total))


def fair_offer(co, investor_id, rating, players=1):
    """The formula investor's offer: {"amount", "post", "bp", "fair" (the post-money it thinks is fair), "score"}."""
    rules = config.ROUNDS[co["stage"]]
    points = score(co, rating, players)
    cfo = 1 + config.CFO_VALUATION_BONUS if ventures_sim.has_role(co, "cfo") else 1
    fair = max(rules["floor"], ventures_sim.valuation(co)) * (0.85 + 0.3 * points) * factor(co, investor_id) * cfo
    amount = rules["raise"] * (0.7 + 0.6 * points)
    return {**fit(co, amount, fair), "fair": int(fair), "score": points}


def fit(co, amount, post):
    """Keep the amount in [0.5x, 1.5x] the typical raise and the equity in the stage's band (moving the post-money)."""
    rules = config.ROUNDS[co["stage"]]
    amount = int(max(rules["raise"] * 0.5, min(rules["raise"] * 1.5, amount)))
    low, high = rules["equity"]
    post = max(amount / (high / 100), min(amount / (low / 100), post))
    return {"amount": amount, "post": int(post), "bp": round(amount / int(post) * cap_table.TOTAL)}


def clamp(co, fair, amount, valuation):
    """What the AI suggested, made safe: numbers it can't send are the fair ones, and the rest stays near fair."""
    def number(value, default):
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else default
    post = max(fair["fair"] * 0.7, min(fair["fair"] * 1.3, number(valuation, fair["post"])))
    return fit(co, number(amount, fair["amount"]), post)


# ---------------------------------------------------------------- term sheets

def new_sheet(co, investor_id, offer, source, message):
    return {"id": f"{co['id']}-{co['stage']}-{int(time.time() * 1000) % 10**9}", "company": co["id"],
            "investor": investor_id, "stage": co["stage"], "amount": offer["amount"], "post": offer["post"],
            "bp": offer["bp"], "fair": offer.get("fair", offer["post"]), "expires": time.time() + config.TERM_SHEET_HOURS * 3600,
            "countered": False, "source": source, "message": message}


def next_stage(stage):
    return config.STAGES[config.STAGES.index(stage) + 1]


def accept(co, sheet):
    """The money arrives: the investor's shares dilute everyone, the Seed round adds the option pool."""
    if co["stage"] == "preseed" and cap_table.POOL not in co["cap"]:
        co = ventures_team.dilute(co, cap_table.POOL, config.OPTION_POOL_PERCENT * 100)
    co = ventures_team.dilute(co, cap_table.investor(sheet["investor"]), sheet["bp"])
    cap = co["cap"]
    entry = {"stage": next_stage(co["stage"]), "investor": sheet["investor"], "amount": sheet["amount"],
             "post": sheet["post"], "bp": sheet["bp"], "age": co["age"]}
    return {**co, "cap": cap, "cash": co["cash"] + sheet["amount"], "raised": co["raised"] + sheet["amount"],
            "stage": next_stage(co["stage"]), "stage_ticks": 0, "pitches": 0, "angel_bp": 0, "sheet": None,
            "last_post": sheet["post"], "valuation": max(co["valuation"], sheet["post"]),
            "peak": max(co["peak"], sheet["post"]), "rounds": co["rounds"] + [entry], "fumes": co["cash"] + sheet["amount"] < 0,
            "reputation": min(100.0, co["reputation"] + 5), "hype": min(100.0, co["hype"] + 10)}


def counter_result(sheet, valuation):
    """("accepted", post) up to the investor's ceiling, ("halfway", post) a bit above, ("walked", None) beyond."""
    ceiling = sheet["fair"] * (1 + INVESTORS.get(sheet["investor"], INVESTORS["maya"])["flex"])
    if valuation <= ceiling:
        return "accepted", int(max(valuation, 1))
    if valuation <= ceiling * config.COUNTER_HALFWAY:
        return "halfway", int(min(ceiling, (sheet["post"] + valuation) / 2))
    return "walked", None


def with_post(co, sheet, post):
    """The same money at a new post-money (inside the equity band)."""
    return {**sheet, **fit(co, sheet["amount"], post), "countered": True}


def card(sheet):
    """The term sheet as text (old apps) and as the optional "term_sheet" field (the website's card)."""
    pre = sheet["post"] - sheet["amount"]
    hours = max(1, math.ceil((sheet["expires"] - time.time()) / 3600))
    counter = "" if sheet["countered"] else " · /offer counter <valuation>"
    text = (f"📄 Term sheet from {investor_title(sheet['investor'])} · {stage_name(next_stage(sheet['stage']))}\n"
            f"{money(sheet['amount'])} for {cap_table.percent_text(sheet['bp'])} · pre-money {money(pre)} · "
            f"post-money {money(sheet['post'])} · 1× liquidation preference\n"
            f"Expires in {hours} h. CEO: /offer accept · /offer decline{counter}")
    field = {"id": sheet["id"], "investor": investor_title(sheet["investor"]), "round": next_stage(sheet["stage"]),
             "amount": sheet["amount"], "equity_bp": sheet["bp"], "pre": pre, "post": sheet["post"],
             "expires": int(sheet["expires"]), "can_counter": not sheet["countered"]}
    return text, field


def offer_sheet(co, sheet, raw=None):
    """A new term sheet: saved, logged, and its card goes to every member."""
    co = ventures_store.put({**co, "sheet": sheet, "last_investor": sheet["investor"]})
    ventures_log.record_offer(sheet, "offered", raw)
    text, field = card(sheet)
    for login in ventures_store.members(co):
        rooms.tell(login, text, "event", term_sheet=field)
    storage.save_data()
    return co


def close_sheet(co, why):
    sheet = co["sheet"]
    ventures_log.record_offer(sheet, why)
    packet = {"type": "term_sheet_closed", "id": sheet["id"], "why": why}
    for login in ventures_store.members(co):
        if login in state.online:
            state.online[login].send(packet)
    return ventures_store.put({**co, "sheet": None})


def take_offer(client, co):
    """/offer accept."""
    sheet = co["sheet"]
    co = close_sheet(co, "accepted")
    co = ventures_store.put(accept(co, sheet))
    news = (f"💰 {co['name']} raised {money(sheet['amount'])} ({stage_name(co['stage'])}) from "
            f"{investor_title(sheet['investor'])} at a {money(sheet['post'])} valuation!")
    rooms.announce(news)   # 📰 big news for everyone
    ventures_team.send_event(co, "round", news)
    storage.save_data()


def counter(client, co, args):
    """/offer counter 90M: once; the formula decides (docs: V7)."""
    sheet = co["sheet"]
    if sheet["countered"]:
        return client.say("📄 You already countered this one. /offer accept or /offer decline", "error")
    wanted = parse_money(args)
    if wanted is None:
        return client.say("Usage: /offer counter <post-money valuation>, like /offer counter 15M", "error")
    if wanted <= sheet["post"]:
        return client.say(f"📄 A counter asks for a HIGHER valuation than {money(sheet['post'])}. "
                          f"To take this one: /offer accept", "error")
    why, post = counter_result(sheet, wanted)
    who = investor_title(sheet["investor"])
    if why == "walked":
        close_sheet(co, "walked")
        storage.save_data()
        line = f"🚪 {who} walked away: \"{money(wanted)}? We're too far apart.\""
        ventures_team.tell_company(co, line)
        if client.room != co["group"]:
            client.say(line)
        return
    new_sheet_ = with_post(co, sheet, post)
    reply = "Deal at your number." if why == "accepted" else f"Let's meet in the middle: {money(new_sheet_['post'])}."
    ventures_store.put({**co, "sheet": new_sheet_})
    ventures_log.record_offer(sheet, "countered")
    text, field = card(new_sheet_)
    for login in ventures_store.members(co):
        rooms.tell(login, f"🤝 {who}: \"{reply}\"\n{text}", "event", term_sheet=field)
    storage.save_data()


def parse_money(text):
    """"90M", "1.5b", "$250K", "12000000" -> dollars (None if it isn't a positive amount)."""
    found = re.fullmatch(r"\$?(\d+(?:\.\d+)?)([kmb]?)", text.strip().lower().replace(",", ""))
    if not found:
        return None
    if len(found.group(1)) > 15:
        return None
    number = float(found.group(1)) * {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[found.group(2)]
    return int(number) if 0 < number <= 1e15 else None


def angel_terms(co, tokens):
    """(dollars, bp) for an angel's 🪙: priced at the company's valuation (at least half the stage's floor)."""
    dollars = tokens * config.ANGEL_DOLLARS_PER_TOKEN
    rules = config.ROUNDS.get(co["stage"], config.ROUNDS["seed"])
    pre = max(ventures_sim.valuation(co), rules["floor"] * 0.5)
    return dollars, round(dollars / (pre + dollars) * cap_table.TOTAL)


# ---------------------------------------------------------------- bridge rounds

def bridge_terms(co):
    """(amount, post, bp): a small round at a low price that keeps the lights on."""
    stage = co["stage"] if config.ROUNDS.get(co["stage"], {}).get("raise") else "b"
    amount = int(config.ROUNDS[stage]["raise"] * config.BRIDGE_RAISE)
    post = int(config.ROUNDS[stage]["floor"] * config.BRIDGE_VALUATION)
    return amount, post, round(amount / post * cap_table.TOTAL)


def bridge(client, co, args):
    """/company bridge: once per stage, when on fumes or out of pitches."""
    if ventures_team.ceo_of(co) != client.key:
        return client.say("👑 Only the CEO can take a bridge round (it dilutes everyone).", "error")
    if co["stage"] not in config.ROUNDS:
        return client.say("🔔 A public company doesn't need a bridge.", "error")
    if co["bridged"] == co["stage"]:
        return client.say("🌉 A bridge round happens only once per stage.", "error")
    if not (co["fumes"] or co["pitches"] >= config.PITCHES_PER_STAGE):
        return client.say("🌉 Bridge Capital only helps companies on fumes or out of pitches for this stage.", "error")
    amount, post, bp = bridge_terms(co)
    co = ventures_team.dilute(co, cap_table.investor("bridge"), bp)
    cash = co["cash"] + amount
    co = ventures_store.put({**co, "cash": cash, "raised": co["raised"] + amount, "bridged": co["stage"],
                             "fumes": co["fumes"] and cash < 0,
                             "rounds": co["rounds"] + [{"stage": "bridge", "investor": "bridge", "amount": amount,
                                                        "post": post, "bp": bp, "age": co["age"]}]})
    line = (f"🌉 Bridge Capital lent a hand: {money(amount)} for {cap_table.percent_text(bp)} "
            f"(at a {money(post)} valuation). Cash: {money(cash)}.")
    ventures_team.tell_company(co, line)
    if client.room != co["group"]:
        client.say(line)
    storage.save_data()


# ---------------------------------------------------------------- the clock and the status

def expire_due(now=None):
    """Called every minute: term sheets past their time close (the angels' offers come back, see ventures_angels)."""
    now = time.time() if now is None else now
    for co in ventures_store.alive():
        if co["sheet"] and co["sheet"]["expires"] <= now:
            close_sheet(co, "expired")
            ventures_team.tell_company(co, f"⌛ The term sheet from {investor_title(co['sheet']['investor'])} expired.")
            storage.save_data()


def refill_pitches(tick):
    """Every PITCH_REFILL_TICKS days stuck without pitches, one more."""
    for co in ventures_store.alive():
        if co["pitches"] >= config.PITCHES_PER_STAGE and co["stage_ticks"] % config.PITCH_REFILL_TICKS == 0:
            ventures_store.put({**co, "pitches": co["pitches"] - 1})


def interest(co, players=1):
    """How investors feel about the next round right now (with an average pitch)."""
    points = score(co, 5, players)
    if points < config.PASS_BELOW:
        return "🥶 low: they'll pass. Beat the milestones by more (MRR, quality, hype and reputation all count)"
    if points < 0.5:
        return "🙂 fair: a good pitch can get a term sheet"
    return "🔥 hot: expect a strong offer"


def status_lines(co):
    lines = []
    if co["stage"] in config.ROUNDS and co["stage"] != "c":
        players = len(ventures_store.members(co))
        lines.append(f"🎤 Pitches left this stage: {max(0, config.PITCHES_PER_STAGE - co['pitches'])} · "
                     f"investor interest: {interest(co, players)}")
    if co["sheet"]:
        lines.append(card(co["sheet"])[0])
    return lines


ventures_tick.on_tick(refill_pitches)
