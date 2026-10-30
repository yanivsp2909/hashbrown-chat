"""
📈 The stock market: four fake companies (config.STOCKS) whose prices take a random walk every STOCK_TICK_SECONDS:
a small random step (STOCK_VOLATILITY_PERCENT), a gentle pull back toward the starting price (so nothing runs off
forever), at most STOCK_MAX_MOVE_PERCENT a tick, never below STOCK_MIN_PRICE. Every tick is ONE broadcast packet:
    {"type": "market", "prices": {"FRY": 101, ...}, "changes": {"FRY": 1.0, ...}, "time": ...}
Shares live in each account's "portfolio" ({symbol: shares}); "spent" remembers what you paid, for your profit.
"""
import random
import time
from collections import deque

from chatserver import config, fund, rooms, state

_listeners = []   # functions(old_prices, new_prices) run after every tick (market news uses this)


def ensure():
    """Every stock exists (a new server, or one from before the market)."""
    for sym, (_, _, start) in config.STOCKS.items():
        state.stocks.setdefault(sym, {"price": start, "open": start, "history": deque(maxlen=config.STOCK_HISTORY_POINTS)})


def step(price, start):
    move = price * random.gauss(0, config.STOCK_VOLATILITY_PERCENT / 100)
    move += (start - price) * config.STOCK_PULL_PERCENT / 100
    limit = max(1, price * config.STOCK_MAX_MOVE_PERCENT // 100)
    return max(config.STOCK_MIN_PRICE, price + int(max(-limit, min(limit, round(move)))))


def prices():
    return {sym: s["price"] for sym, s in state.stocks.items()}


def changes():
    """Percent since the day opened, per stock."""
    return {sym: round((s["price"] - s["open"]) * 100 / s["open"], 1) if s["open"] else 0.0 for sym, s in state.stocks.items()}


def tick(broadcast=True):
    """One minute on the market: every price moves, the history grows, one packet goes to everyone."""
    ensure()
    old = prices()
    now = time.time()
    for sym, s in state.stocks.items():
        if sym in config.STOCKS:
            s["price"] = step(s["price"], config.STOCKS[sym][2])
            s["history"].append((int(now), s["price"]))
    from chatserver import group_stocks   # (group_stocks uses the fund and rooms: importing it at the top would loop)
    group_stocks.tick()
    for listener in list(_listeners):
        listener(old, prices())
    if broadcast:
        packet = {"type": "market", "prices": prices(), "changes": changes(), "time": int(now)}
        for c in list(state.online.values()):
            c.send(packet)


def new_day():
    """Each day's "open" price, for the day's change."""
    for s in state.stocks.values():
        s["open"] = s["price"]


def symbol(text):
    """"fry" -> "FRY"; "#Potatoes" -> "#potatoes" (a group stock); None if there's no such stock."""
    text = text.strip()
    if text.startswith("#"):
        sym = "#" + text[1:].lower()
        return sym if sym in state.stocks else None
    sym = text.upper()
    return sym if sym in state.stocks else None


def shown(sym):
    """How a symbol is written to people: FRY, #POTATOES."""
    return sym.upper()


def trade(client, sym, shares, buying):
    """/buy SYM n and /sell SYM n. Returns an error text or None."""
    account = state.accounts[client.key]
    price = state.stocks[sym]["price"]
    held = account["portfolio"].get(sym, 0)
    cost = price * shares
    charge = fund.fee(cost, config.TRADE_FEE_PERCENT)
    if buying:
        if held + shares > config.MAX_SHARES:
            return f"📈 You can hold at most {config.MAX_SHARES} shares of one stock."
        if account["tokens"] < cost + charge:
            return f"💸 {shares} {shown(sym)} cost {cost} 🪙 + {charge} 🪙 fee. You can't afford that."
        account["tokens"] -= cost + charge
        account["portfolio"] = {**account["portfolio"], sym: held + shares}
        account["spent"] = {**account["spent"], sym: account["spent"].get(sym, 0) + cost}
        verb = "bought"
    else:
        if held < shares:
            return f"📈 You only have {held} {shown(sym)}."
        account["tokens"] += cost - charge
        left = held - shares
        spent = account["spent"].get(sym, 0)
        account["portfolio"] = {k: v for k, v in {**account["portfolio"], sym: left}.items() if v}
        account["spent"] = {k: v for k, v in {**account["spent"], sym: spent * left // held if held else 0}.items() if v}
        verb = "sold"
    fund.collect(charge, "trade fee")
    client.say(f"📈 You {verb} {shares} {shown(sym)} at {price} 🪙 = {cost} 🪙 (fee {charge} 🪙). "
               f"You have {account['tokens']} 🪙.", "money")
    return None


def listing():
    lines = ["📈 Stocks (prices move every minute; /buy FRY 5, /sell FRY 5, /portfolio):"]
    change = changes()
    for sym, (icon, name, _) in config.STOCKS.items():
        arrow = "▲" if change[sym] > 0 else "▼" if change[sym] < 0 else "·"
        lines.append(f"  {icon} {sym}  {name}  {state.stocks[sym]['price']} 🪙  {arrow} {change[sym]:+.1f}% today")
    groups = [(sym, s) for sym, s in state.stocks.items() if sym.startswith("#") and sym[1:] in state.groups]
    if groups:
        lines.append("Group stocks (they follow the group's bank, members and chat; /buy #Name 3):")
        for sym, s in sorted(groups, key=lambda pair: -pair[1]["price"])[:10]:
            lines.append(f"  👥 #{state.groups[sym[1:]]['name']}  {s['price']} 🪙  "
                         f"{(s['price'] - s['open']) * 100 / s['open'] if s['open'] else 0:+.1f}% today")
    lines.append(f"  Trading fee {config.TRADE_FEE_PERCENT}% (at least 1 🪙), into the public fund.")
    return "\n".join(lines)


def portfolio_text(key):
    account = state.accounts[key]
    if not account["portfolio"]:
        return "📈 Your portfolio is empty. See /stocks, then /buy FRY 5"
    lines = ["📈 Your portfolio:"]
    total = 0
    for sym, shares in account["portfolio"].items():
        worth = state.stocks[sym]["price"] * shares if sym in state.stocks else 0
        total += worth
        profit = worth - account["spent"].get(sym, 0)
        lines.append(f"  {sym}  {shares} shares  worth {worth} 🪙  ({profit:+d} 🪙)")
    lines.append(f"  Total  {total} 🪙")
    return "\n".join(lines)


def info_packet(key):
    """{"type": "market_info"} for the website's market screen: every stock with its recent prices, and your shares."""
    ensure()
    account = state.accounts[key]
    change = changes()
    return {"type": "market_info", "fee_percent": config.TRADE_FEE_PERCENT, "tokens": account["tokens"],
            "portfolio": dict(account["portfolio"]), "spent": dict(account["spent"]),
            "stocks": {sym: {"icon": icon, "name": name, "price": state.stocks[sym]["price"], "change": change[sym],
                             "history": [list(p) for p in list(state.stocks[sym]["history"])[-config.MARKET_CHART_POINTS:]]}
                       for sym, icon, name in all_listed()}}


def all_listed():
    """(symbol, icon, name) of the companies, then the groups."""
    rows = [(sym, icon, name) for sym, (icon, name, _) in config.STOCKS.items()]
    for sym in state.stocks:
        if sym.startswith("#") and sym[1:] in state.groups:
            group = state.groups[sym[1:]]
            rows.append((sym, group["emoji"] or "👥", f"#{group['name']}"))
    return rows


def on_tick(listener):
    _listeners.append(listener)


def announce_move(text):
    rooms.announce(text, "event")
