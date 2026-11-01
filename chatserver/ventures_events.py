"""
🌪️ Market events (docs/VENTURES.md, section 8): at each of EVENT_HOURS (Israel time) one event hits a sector or
one company. Hashbrown picks it from a FIXED LIST and writes the headline; the server decides every effect from
the kind and a strength of 1-3. Without the AI a template event is used. Effects that last are kept in
state.ventures["events"] until their last game day; one-shot effects (viral, scandal, outage...) hit at once.
"""
import random

from chatserver import config, history, ventures_ai, ventures_news, ventures_sectors, ventures_store
from chatserver.hashbrown_text import israel_now

STRENGTH = {1: 0.10, 2: 0.25, 3: 0.40}
# kind: (who it targets, does it last, one-line template with {sector} / {company})
KINDS = {
    "demand_up": ("sector", True, "Everyone wants {sector} right now: demand +{pct}% for {days} days"),
    "demand_down": ("sector", True, "Buyers are tired of {sector}: demand -{pct}% for {days} days"),
    "compute_price": ("ai", True, "GPU {updown}: compute costs {sign}{pct}% for {days} days"),
    "chip_shortage": ("hardware", True, "Chip shortage! Hardware units cost +{pct}% for {days} days"),
    "breach_wave": ("cyber", True, "A wave of hacks: everyone needs security, cyber demand +{pct}% for {days} days"),
    "talent_war": ("sector", True, "Talent war in {sector}: salaries +{pct}% for {days} days"),
    "market_mood": ("all", True, "Investors are {mood}: valuations {sign}{pct}% for {days} days"),
    "viral": ("company", False, "{company} went viral! Hype +{points}"),
    "scandal": ("company", False, "Scandal at {company}: reputation -{points}"),
    "outage": ("company", False, "{company} had a big outage: {pct}% of its customers left"),
    "regulation": ("ai", False, "New AI rules: labs with a low safety score lose reputation"),
}
EVENT_FORMAT = ventures_ai.schema("market_event", {
    "kind": {"type": "string", "enum": list(KINDS)}, "direction": {"type": "string", "enum": ["up", "down"]},
    "sector": {"type": "string", "enum": list(config.SECTORS) + ["all"]}, "company": {"type": "string"},
    "strength": {"type": "integer"}, "days": {"type": "integer"},
    "headline": {"type": "string"}, "text": {"type": "string"}})


def active():
    """Events still in force (their effects for the tick: demand, churn, salary, mood)."""
    tick = ventures_store.ensure()["tick"]
    return [e for e in ventures_store.ensure()["events"] if e.get("until", -1) >= tick]


def world_effects():
    """(the events for ventures_sectors.effects, the market mood, compute and unit cost factors)."""
    events, mood, compute, chips = active(), 1.0, 1.0, 1.0
    for e in events:
        mood *= e.get("mood", 1.0)
        compute *= e.get("compute", 1.0)
        chips *= e.get("chips", 1.0)
    return events, mood, compute, chips


# ---------------------------------------------------------------- making one

def maybe_run(now=None):
    """Called every minute: at each event hour, one event (if there are live companies)."""
    now = now or israel_now()
    today = now.date().isoformat()
    slots = ventures_store.ensure().get("event_slots", {})
    done = slots.get("done", []) if slots.get("day") == today else []
    due = [h for h in config.EVENT_HOURS if h <= now.hour and h not in done]
    if not due or not ventures_store.alive():
        return False
    ventures_store.set_field("event_slots", {"day": today, "done": done + due})
    start(random.Random())
    return True


def start(rng):
    """One event: the AI's (checked) or a template's."""
    companies = ventures_store.alive()
    names = {co["name"].lower(): co for co in companies}
    listing = "\n".join(f"- {co['name']}: {config.SECTORS[co['sector']]['name']}, {co['stage']}, hype {co['hype']:.0f}, "
                        f"reputation {co['reputation']:.0f}" for co in companies[:20])
    recent = "; ".join(e["headline"] for e in ventures_store.ensure()["events"][-5:]) or "none"
    language = ventures_ai.language(" ".join(m.get("text", "") for m in history.recent("lobby", 50)))
    instructions = ("You are the game master of \"Hashbrown Ventures\", a startup game in a school chat. Invent ONE market "
                    "event that fits the live companies. Choose \"kind\" from the list only; the game decides the numbers "
                    "from \"strength\" (1-3) and \"days\" (1-5). For a one-company kind, \"company\" is one name from the "
                    "list, otherwise \"\". \"headline\" at most 90 characters, \"text\" one or two short sentences. "
                    f"Don't repeat these recent events: {recent}. Answer in {language}. Reply only with JSON.")
    ventures_ai.ask_json(instructions, f"Live companies:\n{listing}", EVENT_FORMAT,
                         lambda answer: check(answer, names), lambda event: apply_event(event, rng),
                         lambda: apply_event(template(rng, companies), rng))


def check(answer, names):
    kind = ventures_ai.choice_field(answer, "kind", list(KINDS))
    if kind is None:
        return None
    target = KINDS[kind][0]
    company = names.get(str(answer.get("company", "")).strip().lower()) if target == "company" else None
    if target == "company" and company is None:
        return None
    sector = ventures_ai.choice_field(answer, "sector", list(config.SECTORS) + ["all"]) or "all"
    return {"kind": kind, "direction": ventures_ai.choice_field(answer, "direction", ("up", "down")) or "up",
            "sector": target if target in config.SECTORS else sector, "company": company["id"] if company else "",
            "strength": ventures_ai.int_field(answer, "strength", 1, 3) or 2,
            "days": ventures_ai.int_field(answer, "days", 1, 5) or 3,
            "headline": ventures_ai.text_field(answer, "headline", 90), "text": ventures_ai.text_field(answer, "text", 280) or ""}


def template(rng, companies):
    """An event without the AI."""
    kind = rng.choice(list(KINDS))
    target = KINDS[kind][0]
    company = rng.choice(companies) if target == "company" else None
    sector = target if target in config.SECTORS else rng.choice(list(config.SECTORS)) if target == "sector" else "all"
    return {"kind": kind, "direction": rng.choice(["up", "down"]), "sector": sector,
            "company": company["id"] if company else "", "strength": rng.randint(1, 3), "days": rng.randint(1, 5),
            "headline": None, "text": ""}


def effect(event):
    """The numbers an event really has: from the server's table only."""
    kind, part, days = event["kind"], STRENGTH[event["strength"]], event["days"]
    up = event["direction"] == "up"
    fields = {"demand_up": {"demand": 1 + part}, "demand_down": {"demand": 1 - part},
              "compute_price": {"compute": 1 + part if up else 1 - part}, "chip_shortage": {"chips": 1 + part},
              "breach_wave": {"demand": 1 + part * 1.5}, "talent_war": {"salary": 1 + part / 2},
              "market_mood": {"mood": 1 + part / 2 if up else 1 - part / 2}}.get(kind, {})
    return fields, days


def apply_event(event, rng):
    """Put an event into the game: lasting effects into the list, one-shot ones onto the company at once."""
    tick = ventures_store.ensure()["tick"]
    fields, days = effect(event)
    company = ventures_store.get(event["company"]) if event["company"] else None
    headline = event.get("headline") or template_headline(event, company)
    if KINDS[event["kind"]][1]:
        entry = {**event, **fields, "headline": headline, "until": tick + days, "id": f"e{tick}-{rng.randint(0, 9999)}"}
        ventures_store.set_field("events", (ventures_store.ensure()["events"] + [entry])[-20:])
    else:
        hit_now(event, company)
    ventures_news.add("event", f"🌪️ {headline}", company, event.get("text", ""), big=True)
    set_market()


def hit_now(event, company):
    points = {1: 10, 2: 20, 3: 30}[event["strength"]]
    if event["kind"] == "viral" and company:
        ventures_store.put({**company, "hype": min(100.0, company["hype"] + points)})
    elif event["kind"] == "scandal" and company:
        ventures_store.put({**company, "reputation": max(0.0, company["reputation"] - points * 2 // 3)})
    elif event["kind"] == "outage" and company:
        ventures_store.put({**company, "customers": company["customers"] * (1 - STRENGTH[event["strength"]] / 4)})
    elif event["kind"] == "regulation":
        for co in ventures_store.alive():
            if co["sector"] == "ai" and ventures_sectors.state(co)["safety"] < 50:
                ventures_store.put({**co, "reputation": max(0.0, co["reputation"] - points // 2)})


def template_headline(event, company):
    fields, _ = effect(event)   # (the headline says exactly what the effect does)
    factor = next(iter(fields.values()), 1 + STRENGTH[event["strength"]])
    part = round(abs(factor - 1) * 100)
    if event["kind"] == "outage":
        part = round(STRENGTH[event["strength"]] * 25)
    up = event["direction"] == "up"
    return KINDS[event["kind"]][2].format(
        sector=config.SECTORS.get(event["sector"], {}).get("name", "startups"), company=company["name"] if company else "a startup",
        pct=part, days=event["days"], points={1: 10, 2: 20, 3: 30}[event["strength"]],
        updown="prices jump" if up else "prices drop", sign="+" if up else "-", mood="excited" if up else "nervous")


def set_market():
    """The compute and chip prices the actions see right now."""
    _, _, compute, chips = world_effects()
    ventures_sectors.set_market(compute, chips)


def expire():
    """At the tick: events past their last day are forgotten."""
    tick = ventures_store.ensure()["tick"]
    kept = [e for e in ventures_store.ensure()["events"] if e.get("until", -1) >= tick]
    if len(kept) != len(ventures_store.ensure()["events"]):
        ventures_store.set_field("events", kept)
    set_market()
