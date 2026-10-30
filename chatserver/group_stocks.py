"""
👥📈 Group stocks: every group is also a stock, "#name" (bought and sold like FRY: /buy #Potatoes 3).
Its price moves GROUP_STOCK_FOLLOW_PERCENT of the way toward a target every market tick:
    GROUP_STOCK_BASE + bank / GROUP_STOCK_BANK_PER_POINT + members x GROUP_STOCK_PER_MEMBER
    + chat lines in the last hour x GROUP_STOCK_PER_MESSAGE
A group that grew since yesterday (more members or a bigger bank) pays a daily dividend of GROUP_DIVIDEND_PERCENT
of its price per share, from its own bank (never more than GROUP_DIVIDEND_MAX_BANK_PERCENT of the bank).
A disbanded group's shares are paid out at the last price.
"""
import time
from collections import deque

from chatserver import config, fund, rooms, state


def symbol_of(key):
    return f"#{key}"


def note_message(room, who=""):
    """A chat line in a group: it counts toward how busy the group is."""
    if room in state.groups:
        times = state.group_activity.setdefault(room, deque())
        times.append((time.time(), who))
        while times and time.time() - times[0][0] > 3600:
            times.popleft()


def busy(key):
    """Chat lines in the last hour, but at most GROUP_STOCK_MSGS_PER_MEMBER from each person and
    GROUP_STOCK_MAX_BUSY in all (one person spamming their own group can't pump its stock)."""
    now = time.time()
    per_person = {}
    for when, who in state.group_activity.get(key, ()):
        if now - when < 3600:
            per_person[who] = per_person.get(who, 0) + 1
    return min(config.GROUP_STOCK_MAX_BUSY, sum(min(n, config.GROUP_STOCK_MSGS_PER_MEMBER) for n in per_person.values()))


def target(key):
    group = state.groups[key]
    return (config.GROUP_STOCK_BASE + group["bank"] // config.GROUP_STOCK_BANK_PER_POINT
            + len(group["members"]) * config.GROUP_STOCK_PER_MEMBER + busy(key) * config.GROUP_STOCK_PER_MESSAGE)


def tick():
    """Every market tick: each group's price moves toward its target (and new groups get a stock)."""
    now = int(time.time())
    for key in list(state.groups):
        sym = symbol_of(key)
        goal = target(key)
        stock = state.stocks.setdefault(sym, {"price": goal, "open": goal, "history": deque(maxlen=config.STOCK_HISTORY_POINTS)})
        gap = goal - stock["price"]
        step = gap * config.GROUP_STOCK_FOLLOW_PERCENT // 100 or (1 if gap > 0 else -1 if gap < 0 else 0)
        stock["price"] = max(config.STOCK_MIN_PRICE, stock["price"] + step)
        stock["history"].append((now, stock["price"]))
    for sym in [s for s in state.stocks if s.startswith("#") and s[1:] not in state.groups]:
        del state.stocks[sym]   # (a group that's gone and wasn't paid out by forget(): just drop it)


def holders(sym):
    return [(key, a["portfolio"][sym]) for key, a in state.accounts.items() if a["portfolio"].get(sym)]


def pay_dividends():
    """Once a day: groups that grew pay their shareholders from the bank. Then today's size is remembered."""
    sizes = state.economy_extra.get("group_size", {})
    for key, group in state.groups.items():
        sym = symbol_of(key)
        members, bank = sizes.get(key, [len(group["members"]), group["bank"]])
        grew = len(group["members"]) > members or group["bank"] > bank
        owners = holders(sym)
        if not grew or not owners or sym not in state.stocks:
            continue
        per_share = max(1, state.stocks[sym]["price"] * config.GROUP_DIVIDEND_PERCENT // 100)
        budget = group["bank"] * config.GROUP_DIVIDEND_MAX_BANK_PERCENT // 100
        total = per_share * sum(n for _, n in owners)
        if total > budget:   # not enough: everyone gets the same smaller share
            per_share = budget // max(1, sum(n for _, n in owners))
        for login, shares in owners:
            paid = per_share * shares
            if paid:
                group["bank"] -= paid
                state.accounts[login]["tokens"] += paid
                rooms.tell(login, f"💸 {rooms.room_title(key)} grew, so it paid you a dividend: {paid} 🪙 "
                                  f"({per_share} 🪙 x {shares} shares).", "money")
    state.economy_extra = {**state.economy_extra,
                           "group_size": {k: [len(g["members"]), g["bank"]] for k, g in state.groups.items()}}


def forget(key):
    """The group was disbanded: its shareholders are paid the last price (from the fund first), the stock goes."""
    sym = symbol_of(key)
    state.group_activity.pop(key, None)   # (a new group with this name starts quiet)
    stock = state.stocks.pop(sym, None)
    if stock is None:
        return
    for login, shares in holders(sym):
        account = state.accounts[login]
        account["portfolio"] = {k: v for k, v in account["portfolio"].items() if k != sym}
        account["spent"] = {k: v for k, v in account["spent"].items() if k != sym}
        fund.pay_prize(login, shares * stock["price"])
        rooms.tell(login, f"💸 {sym} was disbanded: your {shares} shares were paid out at {stock['price']} 🪙 each.", "money")
