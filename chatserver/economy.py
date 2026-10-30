"""
💹 The economy's saved state and its once-a-day jobs. chat_data.json gets one "economy" key:
    {"fund": public fund, "stocks": {symbol: {price, open, history}}, "supply": [[day, total tokens], ...]}
(Older files don't have it: everything starts fresh.) Each account gets "portfolio" and "spent" for stocks.
"""
from collections import deque

from chatserver import config, group_stocks, market, market_news, savings, state, textutil  # noqa: F401 (news listens to ticks)

_daily_jobs = []   # functions run once a day (dividends, interest, loans...), in the order they were added


def account_defaults():
    return {"portfolio": {}, "spent": {}, **savings.account_defaults()}


def total_supply():
    """Every token in the game: wallets, savings, group banks, the fund, the jackpot and Hashbrown's tips."""
    wallets = sum(a.get("tokens", 0) + a.get("savings", 0) for a in state.accounts.values())
    return wallets + sum(g.get("bank", 0) for g in state.groups.values()) + state.public_fund + state.jackpot \
        + state.hashbrown_tokens


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
    from chatserver import auctions   # (auctions saves through storage: importing it at the top would loop)
    auctions.refund_after_restart()   # 🔨 a held bid goes back
    market.ensure()


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
