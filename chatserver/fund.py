"""
🧾 The public fund: trading fees, the tax on big casino wins and other fees go in; the quest, question-of-the-day
and drawing prizes (and savings interest) come out. Tokens go round instead of being printed, so they keep
their value. Saved in chat_data.json ("economy").
"""
from chatserver import config, state


def collect(amount, why=""):
    """Tax or fee into the fund."""
    if amount > 0:
        state.public_fund += amount
        state.fund_today = {**state.fund_today, "in": state.fund_today.get("in", 0) + amount}


def pay_prize(key, amount):
    """A prize for `key`: from the fund as far as it goes, the rest is new tokens. Returns how much the fund paid."""
    from_fund = min(state.public_fund, amount)
    state.public_fund -= from_fund
    state.accounts[key]["tokens"] += amount
    state.fund_today = {**state.fund_today, "out": state.fund_today.get("out", 0) + from_fund}
    return from_fund


def pay_from_fund_only(key, amount):
    """Only what the fund has (savings interest: when the fund is empty, there's none). Returns what was paid."""
    paid = max(0, min(state.public_fund, amount))
    state.public_fund -= paid
    state.accounts[key]["tokens"] += paid
    return paid


def casino_tax(net_win):
    """The tax on a casino win: CASINO_TAX_PERCENT of wins of at least CASINO_TAX_FROM, 0 otherwise."""
    return net_win * config.CASINO_TAX_PERCENT // 100 if net_win >= config.CASINO_TAX_FROM else 0


def fee(amount, percent):
    """A fee of `percent` (at least 1 token on anything above 0)."""
    return max(1, amount * percent // 100) if amount > 0 else 0
