"""
💹 The economy's saved state and its once-a-day jobs. chat_data.json gets one "economy" key:
    {"fund": public fund, "stocks": {symbol: {price, open, history}}, "supply": [[day, total tokens], ...]}
(Older files don't have it: everything starts fresh.) Each account gets "portfolio" and "spent" for stocks.
"""
from collections import deque
from datetime import datetime, timedelta

from chatserver import config, group_stocks, market, market_news, savings, state, textutil  # noqa: F401 (news listens to ticks)

_daily_jobs = []   # functions run once a day (dividends, interest, loans...), in the order they were added


def account_defaults():
    return {"portfolio": {}, "spent": {}, **savings.account_defaults()}


def total_supply():
    """Every token in the game: wallets, savings, group banks, the fund, the jackpot, Hashbrown's tips and the
    🏢 angel offers waiting for an answer (those tokens are held, not gone)."""
    wallets = sum(a.get("tokens", 0) + a.get("savings", 0) for a in state.accounts.values())
    held = sum(o.get("tokens", 0) for o in (state.ventures or {}).get("angels", {}).values())
    return wallets + sum(g.get("bank", 0) for g in state.groups.values()) + state.public_fund + state.jackpot \
        + state.hashbrown_tokens + held


def to_saved():
    return {"fund": state.public_fund, "day": state.economy_day,
            "stocks": {sym: {"price": s["price"], "open": s["open"], "history": list(s["history"])}
                       for sym, s in state.stocks.items()},
            "supply": state.supply_history[-config.SUPPLY_DAYS_KEPT:], "extra": state.economy_extra}


def load_saved(saved):
    state.public_fund, state.stocks, state.supply_history, state.economy_day = 0, {}, [], ""
    state.economy_extra = {}
    if not isinstance(saved, dict):
        market.ensure()
        return
    fund = saved.get("fund")
    state.public_fund = fund if isinstance(fund, int) and fund >= 0 else 0
    state.economy_day = saved.get("day") if isinstance(saved.get("day"), str) else ""
    for sym, s in (saved.get("stocks") or {}).items():
        if (sym in config.STOCKS or (sym.startswith("#") and sym[1:] in state.groups)) and isinstance(s, dict) and isinstance(s.get("price"), int) and s["price"] >= 1:
            history = [tuple(p) for p in s.get("history", []) if isinstance(p, list) and len(p) == 2]
            state.stocks[sym] = {"price": s["price"], "open": s.get("open") if isinstance(s.get("open"), int) else s["price"],
                                 "history": deque(history, maxlen=config.STOCK_HISTORY_POINTS)}
    supply = saved.get("supply")
    state.supply_history = [list(p) for p in supply if isinstance(p, list) and len(p) == 2] if isinstance(supply, list) else []
    extra = saved.get("extra")
    state.economy_extra = extra if isinstance(extra, dict) else {}
    from chatserver import auctions, marketplace   # (they save through storage: importing them at the top would loop)
    state.economy_extra = marketplace.clean_saved(state.economy_extra)   # 🛒 only well-formed listings
    auctions.refund_after_restart()   # 🔨 a held bid goes back
    market.ensure()
    for key, account in state.accounts.items():   # shares of stocks that don't exist any more: paid what they cost
        lost = [sym for sym in account.get("portfolio", {}) if sym not in state.stocks]
        for sym in lost:
            refund = account.get("spent", {}).get(sym, 0)
            account["portfolio"] = {k: v for k, v in account["portfolio"].items() if k != sym}
            account["spent"] = {k: v for k, v in account.get("spent", {}).items() if k != sym}
            account["tokens"] = account.get("tokens", 0) + refund


def on_new_day(job):
    _daily_jobs.append(job)


on_new_day(group_stocks.pay_dividends)   # 👥 growing groups pay their shareholders
on_new_day(savings.pay_interest)          # 🏦 savings earn interest (from the fund)


def daily_tick():
    """Called every minute: the first call of a new day runs the daily jobs once."""
    today = textutil.today()
    if state.economy_day == today:
        return
    first_ever = state.economy_day == ""
    state.economy_day = today
    market.new_day()
    state.supply_history = (state.supply_history + [[today, total_supply()]])[-config.SUPPLY_DAYS_KEPT:]
    state.fund_today = {}
    if not first_ever:
        for job in list(_daily_jobs):
            job()


def dashboard():
    """{"type": "economy"} for the website's dashboard."""
    total = total_supply()
    richest = sorted(state.accounts.values(), key=lambda a: a.get("tokens", 0), reverse=True)[:config.DASHBOARD_RICHEST]
    change = market.changes()
    hottest = max(change.items(), key=lambda pair: abs(pair[1]), default=None)
    week_ago = next((t for day, t in reversed(state.supply_history[:-1] or [])
                     if day <= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")), None)
    if week_ago is None and len(state.supply_history) >= 1 and state.supply_history[0][0] != textutil.today():
        week_ago = state.supply_history[0][1]   # less than a week of numbers: since the first one
    return {"type": "economy", "total": total, "fund": state.public_fund, "fund_today": dict(state.fund_today),
            "richest": [{"name": a["nick"], "tokens": a.get("tokens", 0)} for a in richest],
            "hottest": {"symbol": hottest[0], "change": hottest[1], "price": state.stocks[hottest[0]]["price"]} if hottest else None,
            "supply": [list(p) for p in state.supply_history[-14:]],
            "inflation_week": round((total - week_ago) * 100 / week_ago, 1) if week_ago else None}
