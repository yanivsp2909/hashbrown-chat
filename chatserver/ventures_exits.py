"""
🚪 Exits: when a company goes public, is bought, or a season ends, its PLAYER holders get personal 🪙 for their
stake (owner's decision V2, docs/VENTURES.md 9.5):

    gross = stake x exit value / EXIT_DOLLARS_PER_TOKEN, at most EXIT_MAX_TOKENS per person per exit
    net   = gross - EXIT_TAX_PERCENT
    paid  = from the public fund first, then new tokens up to VENTURES_MINT_SEASON_CAP for the season;
            what's over the cap waits in the exit queue and is paid from the fund at each tick (oldest first)

The investors (the game's characters), the option pool and the public own the rest: they get nothing in 🪙.
"""
import time

from chatserver import cap_table, config, fund, rooms, state, storage, ventures_store
from chatserver.ventures_text import money


def tokens_for(bp, value):
    """(gross, tax, net) for one stake."""
    gross = min(config.EXIT_MAX_TOKENS, int(bp / cap_table.TOTAL * value / config.EXIT_DOLLARS_PER_TOKEN))
    tax = gross * config.EXIT_TAX_PERCENT // 100
    return gross, tax, gross - tax


def minted_left():
    return max(0, config.VENTURES_MINT_SEASON_CAP - ventures_store.ensure().get("minted", 0))


def pay(login, tokens, why):
    """Pay one person: the fund first, then new tokens while the season's cap allows; the rest waits. Returns
    (from the fund, newly made, waiting)."""
    if login not in state.accounts or tokens <= 0:
        return 0, 0, 0
    from_fund = fund.pay_from_fund_only(login, tokens)
    new = min(tokens - from_fund, minted_left())
    if new:
        state.accounts[login]["tokens"] += new
        ventures_store.set_field("minted", ventures_store.ensure().get("minted", 0) + new)
    waiting = tokens - from_fund - new
    if waiting:
        queue = ventures_store.ensure().get("exit_queue", [])
        ventures_store.set_field("exit_queue", queue + [{"login": login, "tokens": waiting, "why": why, "at": time.time()}])
    return from_fund, new, waiting


def pay_exit(co, value, kind, percent=100):
    """Every player holder of `co` gets their part of an exit worth `value` $ (percent: a season end pays 20%).
    Returns [{login, bp, net, waiting}]."""
    paid = []
    for holder, bp in sorted(co["cap"].items(), key=lambda item: -item[1]):
        if not holder.startswith("p:"):
            continue
        login = holder[2:]
        _, tax, net = tokens_for(bp, value * percent / 100)
        if net <= 0 or login not in state.accounts:
            continue
        _, _, waiting = pay(login, net, f"{co['name']} {kind}")
        paid.append({"login": login, "bp": bp, "net": net, "waiting": waiting})
        later = f" ({waiting:,} of it waits for the public fund)" if waiting else ""
        safe_tell(login, f"🚪 Exit! Your {cap_table.percent_text(bp)} of {co['name']} ({kind}, valued "
                         f"{money(value * percent / 100)}) paid {net:,} 🪙 after {config.EXIT_TAX_PERCENT}% tax{later}.")
    record(co, kind, value, paid)
    storage.save_data()
    return paid


def record(co, kind, value, paid):
    """Kept for the boards and the Hall of Fame."""
    ventures = ventures_store.ensure()
    entry = {"company": co["id"], "name": co["name"], "kind": kind, "value": int(value), "season": ventures["season"],
             "tick": ventures["tick"], "paid": [{"login": p["login"], "tokens": p["net"]} for p in paid]}
    ventures_store.set_field("exits", (ventures.get("exits", []) + [entry])[-config.EXITS_KEPT:])


def pay_queue():
    """At the tick: what waits is paid from the fund, oldest first (never new tokens). The new queue is saved
    before anyone is told, so a broken message can never pay the same thing twice."""
    left, told = [], []
    for item in ventures_store.ensure().get("exit_queue", []):
        if item["login"] not in state.accounts:
            continue
        paid = fund.pay_from_fund_only(item["login"], item["tokens"])
        if paid:
            told.append((item["login"], f"🚪 The public fund paid {paid:,} 🪙 of your exit ({item['why']})."))
        if item["tokens"] - paid > 0:
            left.append({**item, "tokens": item["tokens"] - paid})
    ventures_store.set_field("exit_queue", left)
    for login, text in told:
        safe_tell(login, text)


def safe_tell(login, text):
    try:
        rooms.tell(login, text, "money")
    except Exception:   # (a message must never stop a payout halfway)
        pass


def received(login, season=None):
    """🪙 a person got from exits (this season or all)."""
    return sum(p["tokens"] for e in ventures_store.ensure().get("exits", []) if season is None or e["season"] == season
               for p in e["paid"] if p["login"] == login)
