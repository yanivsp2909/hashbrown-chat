"""
🏢 Hashbrown Ventures' saved records, kept in state.ventures (saved in chat_data.json as "ventures", together with
the accounts, so tokens that move into or out of the game are saved in the same write):

    {"season": 1, "tick": 0, "day": "2026-11-01", "next_id": 2,
     "companies": {"c1": {...one company...}},
     "graveyard": [...], "angels": {...}, "cooldowns": {login: tick}}

A company IS a private group (its chat, members, invites); the group has an extra field "company": "c1".
Company cash is game dollars and never the group's bank. Records are replaced, never changed in place.
"""
import math

from chatserver import cap_table, config, state, textutil, ventures_sectors

STATUSES = ("alive", "dead", "shutdown", "acquired", "ended")
STAFF_KINDS = ("engineer", "sales", "marketer")


def empty():
    return {"season": 1, "tick": 0, "day": "", "next_id": 1, "companies": {}, "graveyard": [],
            "angels": {}, "cooldowns": {}, "angel_days": {},
            "news": [], "news_id": 0, "news_ai": ["", 0],    # 📰 the feed (ventures_news.py)
            "events": [], "event_slots": {},                # 🌪️ market events in force (ventures_events.py)
            "minted": 0, "exit_queue": [], "exits": [],     # 🚪 exits (ventures_exits.py)
            "acquisitions": {}, "partner_offers": {}, "poached": {},   # 🤝 deals waiting (ventures_deals.py)
            "fame": []}                                     # 🏛️ the Hall of Fame (ventures_season.py)


def ensure():
    """Fill in a missing state.ventures (a new server, or the tests' reset)."""
    if not state.ventures:
        state.ventures = empty()
    return state.ventures


def new_company(cid, name, group_key, sector, founder, tick):
    """A brand-new company record (a plain dict, so it saves as JSON)."""
    return {"id": cid, "name": name, "group": group_key, "sector": sector, "stage": "idea", "status": "alive",
            "founder": founder, "founded": tick, "season": state.ventures.get("season", 1) if state.ventures else 1,
            "age": 0, "stage_ticks": 0,
            "cash": config.START_CASH, "quality": float(config.START_QUALITY), "hype": float(config.START_HYPE),
            "reputation": float(config.START_REPUTATION), "customers": 0.0,
            "staff": {kind: 0 for kind in STAFF_KINDS},
            "roles": {founder: "ceo"}, "cap": {cap_table.player(founder): cap_table.TOTAL}, "grants": {},
            "offers": {},        # 📨 invited login -> {"role", "bp"}: what they get when they /join
            "ap": config.AP_BASE, "seen": [founder], "acted": False, "idle": 0, "fumes": False,
            "revenue": 0, "burn": 0, "valuation": 0, "last_post": 0, "peak": 0, "raised": 0, "rounds": [],
            "pivoted": "", "cause": "", "report": "",
            "pitches": 0, "pitch": None, "sheet": None, "last_investor": "", "bridged": "", "angel_bp": 0,
            "angel_in": {},      # 😇 login -> 🪙 they put in as an angel (accepted)
            "reports": [],       # 📊 the last REPORTS_KEPT daily reports: {"age", "text"}
            "pitch_log": [],     # 🎤 the last pitch's conversation: {"who": "investor"|"founders", "name", "text"}
            "sector_state": {**ventures_sectors.default_state(sector), "_sector": sector},   # 🏭 the sector's own numbers
            "partner": {},       # 🤝 {"with": company id, "until": tick} while a partnership lasts
            "synergy": 0.0,      # 🤝 extra new customers for good, from buying a company in another sector
            "ipo": {}}           # 🔔 {"symbol", "value", "tick"} once public


# ---------------------------------------------------------------- finding companies

def companies():
    return ensure()["companies"]


def get(cid):
    return companies().get(cid)


def of_group(key):
    """The company whose group this is (alive or not), or None."""
    group = state.groups.get(key)
    return get(group.get("company", "")) if group else None


def is_company_group(key):
    group = state.groups.get(key)
    return bool(group and group.get("company"))


def members(co):
    group = state.groups.get(co["group"])
    return list(group["members"]) if group else []


def mine(login):
    """The live company this person is in, or None (one at a time)."""
    for co in companies().values():
        if co["status"] == "alive" and login in members(co):
            return co
    return None


def find(name):
    """A company by its name (any case), newest first, or None."""
    wanted = name.strip().lower()
    found = [co for co in companies().values() if co["name"].lower() == wanted]
    return max(found, key=lambda co: int(co["id"][1:])) if found else None


def alive():
    return [co for co in companies().values() if co["status"] == "alive"]


# ---------------------------------------------------------------- changing them

def put(co):
    """Save a new version of a company (the old dict is replaced, not edited). Open Ventures screens refresh."""
    state.ventures_dirty = True
    ventures = ensure()
    state.ventures = {**ventures, "companies": {**ventures["companies"], co["id"]: co}}
    return co


def update(cid, **changes):
    return put({**get(cid), **changes})


def set_field(name, value):
    """A top-level field of state.ventures (tick, day, graveyard...)."""
    state.ventures_dirty = True
    state.ventures = {**ensure(), name: value}


def next_id():
    ventures = ensure()
    set_field("next_id", ventures["next_id"] + 1)
    return f"c{ventures['next_id']}"


# ---------------------------------------------------------------- saving and loading

def to_saved():
    return ensure()


def clean_saved(saved):
    """What chat_data.json had under "ventures", checked: anything malformed is left out. Never raises
    (a crash here would stop the server from starting)."""
    result = empty()
    if not isinstance(saved, dict):
        return result
    if isinstance(saved.get("news"), list):
        result["news"] = [n for n in saved["news"] if isinstance(n, dict) and isinstance(n.get("headline"), str)
                          and is_count(n.get("id"))][-config.NEWS_KEPT:]
    if isinstance(saved.get("events"), list):
        result["events"] = [e for e in saved["events"] if isinstance(e, dict) and isinstance(e.get("kind"), str)
                            and is_count(e.get("until")) and isinstance(e.get("headline"), str)
                            and all(is_number(e.get(k, 1.0)) for k in ("demand", "churn", "salary", "mood", "compute", "chips"))][-20:]
    slots = saved.get("event_slots")
    if isinstance(slots, dict) and isinstance(slots.get("day"), str) and isinstance(slots.get("done"), list):
        result["event_slots"] = {"day": slots["day"], "done": [h for h in slots["done"] if is_count(h)]}
    news_ai = saved.get("news_ai")
    if isinstance(news_ai, list) and len(news_ai) == 2 and isinstance(news_ai[0], str) and is_count(news_ai[1]):
        result["news_ai"] = news_ai
    if isinstance(saved.get("exit_queue"), list):   # 🚪 tokens owed to people: keep every well-formed one
        result["exit_queue"] = [q for q in saved["exit_queue"] if isinstance(q, dict) and isinstance(q.get("login"), str)
                                and is_count(q.get("tokens")) and q["tokens"] > 0 and isinstance(q.get("why"), str)]
    if isinstance(saved.get("exits"), list):
        result["exits"] = [e for e in saved["exits"] if isinstance(e, dict) and is_count(e.get("season"))
                           and is_number(e.get("value")) and isinstance(e.get("paid"), list) and isinstance(e.get("name"), str)
                           and all(isinstance(p, dict) and isinstance(p.get("login"), str) and is_count(p.get("tokens"))
                                   for p in e["paid"])][-config.EXITS_KEPT:]
    if isinstance(saved.get("fame"), list):
        result["fame"] = [f for f in saved["fame"] if isinstance(f, dict) and is_count(f.get("season"))
                          and all(isinstance(f.get(k), str) for k in ("award", "name", "text"))]
    deal_fields = {"acquisitions": (("from", str), ("amount", int), ("at", float)), "partner_offers": (("from", str), ("at", float)),
                   "poached": (("tick", int), ("n", int))}
    for field, needs in deal_fields.items():
        if isinstance(saved.get(field), dict):
            result[field] = {k: v for k, v in saved[field].items() if isinstance(k, str) and isinstance(v, dict)
                             and all(is_number(v.get(n)) if kind is not str else isinstance(v.get(n), str) for n, kind in needs)}
    for field in ("season", "tick", "next_id", "news_id", "minted"):
        if is_count(saved.get(field)):
            result[field] = saved[field]
    if isinstance(saved.get("day"), str):
        result["day"] = saved["day"]
    for field in ("graveyard",):
        if isinstance(saved.get(field), list):
            result[field] = [e for e in saved[field] if isinstance(e, dict)][-config.GRAVEYARD_KEPT:]
    if isinstance(saved.get("cooldowns"), dict):
        result["cooldowns"] = {k: v for k, v in saved["cooldowns"].items() if isinstance(k, str) and is_count(v)}
    if isinstance(saved.get("angel_days"), dict):
        result["angel_days"] = {k: v for k, v in saved["angel_days"].items() if isinstance(k, str) and isinstance(v, list)
                                and len(v) == 2 and isinstance(v[0], str) and is_count(v[1])}
    if isinstance(saved.get("angels"), dict):   # 😇 held tokens: keep every well-formed offer (they're paid back later)
        result["angels"] = {k: o for k, o in saved["angels"].items() if is_angel_offer(k, o)}
    raw = saved.get("companies")
    for cid, co in (raw.items() if isinstance(raw, dict) else []):
        try:
            cleaned = clean_company(cid, co)
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as e:
            textutil.log(f"[VENTURES] ⚠️ Skipped a damaged company record {cid!r} ({type(e).__name__}).")
            cleaned = None
        if cleaned:
            result["companies"][cid] = cleaned
    used = [int(k[1:]) for k in list(result["companies"]) + list(result["angels"]) if k[1:].isdecimal()]
    result["next_id"] = max([result["next_id"]] + [n + 1 for n in used])   # new ids never reuse an old one
    return result


def is_angel_offer(key, o):
    return (isinstance(o, dict) and o.get("id") == key and isinstance(o.get("company"), str)
            and isinstance(o.get("login"), str) and is_count(o.get("tokens")) and o["tokens"] > 0
            and is_number(o.get("at")) and is_count(o.get("dollars", 0)) and is_count(o.get("bp", 0)))


def is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def clean_company(cid, co):
    """One saved company: every field must have the type a new company has; nested tables are checked too."""
    if not (isinstance(cid, str) and isinstance(co, dict) and isinstance(co.get("name"), str)
            and isinstance(co.get("group"), str) and isinstance(co.get("founder"), str)):
        return None
    if co.get("sector") not in config.SECTORS or co.get("stage") not in config.STAGES or co.get("status") not in STATUSES:
        return None
    base = new_company(cid, co["name"], co["group"], co["sector"], co["founder"], 0)
    kept = {}
    for field, default in base.items():
        value = co.get(field, default)
        same_type = (is_number(value) and is_number(default)) or type(value) is type(default)
        kept[field] = value if same_type else default
    kept["staff"] = {kind: int(kept["staff"].get(kind, 0)) if is_count(kept["staff"].get(kind, 0)) else 0
                     for kind in STAFF_KINDS}
    kept["roles"] = {k: v for k, v in kept["roles"].items() if isinstance(k, str) and v in config.ROLES}
    kept["cap"] = cap_table.normalize({h: v for h, v in kept["cap"].items() if isinstance(h, str) and is_count(v)})
    if not kept["cap"] or sum(kept["cap"].values()) != cap_table.TOTAL:   # a broken table: the founder owns it all
        kept["cap"] = {cap_table.player(co["founder"]): cap_table.TOTAL}
    kept["grants"] = {k: g for k, g in kept["grants"].items()
                      if isinstance(g, dict) and is_count(g.get("bp")) and is_count(g.get("tick"))}
    kept["offers"] = {k: o for k, o in kept["offers"].items()
                      if isinstance(o, dict) and o.get("role") in config.ROLES and is_count(o.get("bp"))
                      and is_number(o.get("at", 0))}
    kept["seen"] = [k for k in kept["seen"] if isinstance(k, str)]
    kept["rounds"] = [r for r in kept["rounds"] if isinstance(r, dict)]
    kept["angel_in"] = {k: v for k, v in kept["angel_in"].items() if isinstance(k, str) and is_count(v)}
    kept["reports"] = [r for r in kept["reports"] if isinstance(r, dict) and isinstance(r.get("text"), str)
                       and is_count(r.get("age"))][-config.REPORTS_KEPT:]
    kept["pitch_log"] = [e for e in kept["pitch_log"] if isinstance(e, dict) and isinstance(e.get("text"), str)
                         and e.get("who") in ("investor", "founders") and isinstance(e.get("name"), str)][-config.PITCH_LOG_KEPT:]
    for field in ("cash", "revenue", "burn", "valuation", "last_post", "peak", "raised"):   # (whole dollars)
        kept[field] = int(kept[field])
    kept["sheet"] = clean_sheet(co.get("sheet"), cid, kept["stage"])
    saved_state = co.get("sector_state")   # 🏭 a damaged one starts fresh (a sector state holds no money)
    kept["sector_state"] = saved_state if isinstance(saved_state, dict) and saved_state.get("_sector") == kept["sector"] \
        and set(ventures_sectors.default_state(kept["sector"])) <= set(saved_state) else base["sector_state"]   # 📄 an open term sheet survives a restart (a pitch doesn't)
    return kept


SHEET_NUMBERS = ("amount", "post", "bp", "fair", "expires")


def clean_sheet(sheet, cid, stage):
    if not (isinstance(sheet, dict) and isinstance(sheet.get("id"), str) and isinstance(sheet.get("investor"), str)
            and sheet.get("company") == cid and sheet.get("stage") == stage and stage in config.ROUNDS
            and all(is_number(sheet.get(k)) and sheet[k] >= 0 for k in SHEET_NUMBERS) and sheet["post"] > 0):
        return None
    return {**sheet, "amount": int(sheet["amount"]), "post": int(sheet["post"]), "bp": int(sheet["bp"]),
            "countered": sheet.get("countered") is True}
