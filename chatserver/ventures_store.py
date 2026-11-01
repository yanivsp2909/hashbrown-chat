"""
🏢 Hashbrown Ventures' saved records, kept in state.ventures (saved in chat_data.json as "ventures", together with
the accounts, so tokens that move into or out of the game are saved in the same write):

    {"season": 1, "tick": 0, "day": "2026-11-01", "next_id": 2,
     "companies": {"c1": {...one company...}},
     "graveyard": [...], "angels": {...}, "cooldowns": {login: tick}}

A company IS a private group (its chat, members, invites); the group has an extra field "company": "c1".
Company cash is game dollars and never the group's bank. Records are replaced, never changed in place.
"""
from chatserver import cap_table, config, state, textutil

STATUSES = ("alive", "dead", "shutdown")
STAFF_KINDS = ("engineer", "sales", "marketer")


def empty():
    return {"season": 1, "tick": 0, "day": "", "next_id": 1, "companies": {}, "graveyard": [],
            "angels": {}, "cooldowns": {}}


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
            "pivoted": "", "cause": "", "report": ""}


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
    """Save a new version of a company (the old dict is replaced, not edited)."""
    ventures = ensure()
    state.ventures = {**ventures, "companies": {**ventures["companies"], co["id"]: co}}
    return co


def update(cid, **changes):
    return put({**get(cid), **changes})


def set_field(name, value):
    """A top-level field of state.ventures (tick, day, graveyard...)."""
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
    for field in ("season", "tick", "next_id"):
        if is_count(saved.get(field)):
            result[field] = saved[field]
    if isinstance(saved.get("day"), str):
        result["day"] = saved["day"]
    for field in ("graveyard",):
        if isinstance(saved.get(field), list):
            result[field] = [e for e in saved[field] if isinstance(e, dict)][-config.GRAVEYARD_KEPT:]
    for field in ("angels", "cooldowns"):
        if isinstance(saved.get(field), dict):
            result[field] = saved[field]
    raw = saved.get("companies")
    for cid, co in (raw.items() if isinstance(raw, dict) else []):
        try:
            cleaned = clean_company(cid, co)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            textutil.log(f"[VENTURES] ⚠️ Skipped a damaged company record {cid!r} ({type(e).__name__}).")
            cleaned = None
        if cleaned:
            result["companies"][cid] = cleaned
    return result


def is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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
    kept["grants"] = {k: g for k, g in kept["grants"].items()
                      if isinstance(g, dict) and is_count(g.get("bp")) and is_count(g.get("tick"))}
    kept["offers"] = {k: o for k, o in kept["offers"].items()
                      if isinstance(o, dict) and o.get("role") in config.ROLES and is_count(o.get("bp"))}
    kept["seen"] = [k for k in kept["seen"] if isinstance(k, str)]
    kept["rounds"] = [r for r in kept["rounds"] if isinstance(r, dict)]
    for field in ("cash", "revenue", "burn", "valuation", "last_post", "peak", "raised"):
        kept[field] = int(kept[field])
    return kept
