"""
🏦 Savings and 💳 loans (the bank for people; groups have their own bank).
Savings: /save, /withdraw, /savings. Once a day they earn SAVINGS_INTEREST_PERCENT (at most SAVINGS_INTEREST_MAX),
paid by the public fund: when the fund is empty there's no interest, so no tokens come from nowhere.
Loans: /loan N, /repay [N|all]. One at a time, up to LOAN_MAX, for accounts older than GIVE_MIN_AGE_HOURS. The
loan comes from the fund (new tokens if it's short), you owe LOAN_INTEREST_PERCENT more, due in LOAN_DAYS, and
what you pay back goes into the fund. Late: your per-minute income repays it first.
"""
import time

from chatserver import config, fund, rooms, state, storage


def account_defaults():
    return {"savings": 0, "loan": None}


def amount_of(client, text, most):
    """'50' or 'all' (= most) -> a number, or None (and says how)."""
    text = text.strip().lower()
    if text == "all":
        return most if most > 0 else None
    return int(text) if text.isdecimal() and 0 < int(text) <= 10 ** 9 else None


def save(client, args):
    account = state.accounts[client.key]
    amount = amount_of(client, args, account["tokens"])
    if amount is None:
        return client.say("🏦 Use: /save 100  (or /save all)", "error")
    if amount > account["tokens"]:
        return client.say(f"🏦 You only have {account['tokens']} 🪙.", "error")
    if account["savings"] + amount > config.SAVINGS_MAX:
        return client.say(f"🏦 You can keep at most {config.SAVINGS_MAX} 🪙 in savings.", "error")
    account["tokens"] -= amount
    account["savings"] += amount
    storage.save_data()
    return client.say(f"🏦 You saved {amount} 🪙. Savings: {account['savings']} 🪙 "
                      f"(+{config.SAVINGS_INTEREST_PERCENT}% a day while the public fund can pay it).", "money")


def withdraw(client, args):
    account = state.accounts[client.key]
    amount = amount_of(client, args, account["savings"])
    if amount is None:
        return client.say("🏦 Use: /withdraw 100  (or /withdraw all)", "error")
    if amount > account["savings"]:
        return client.say(f"🏦 You only have {account['savings']} 🪙 in savings.", "error")
    account["savings"] -= amount
    account["tokens"] += amount
    storage.save_data()
    return client.say(f"🏦 You took {amount} 🪙 out. Savings: {account['savings']} 🪙.", "money")


def status_text(key):
    account = state.accounts[key]
    lines = [f"🏦 Savings: {account['savings']} 🪙 (+{config.SAVINGS_INTEREST_PERCENT}% a day, at most "
             f"{config.SAVINGS_INTEREST_MAX} 🪙, paid by the public fund: {state.public_fund} 🪙 in it now)"]
    loan = account["loan"]
    if loan:
        days = (loan["due"] - time.time()) / 86400
        when = f"due in {days:.1f} days" if days > 0 else "LATE: your income pays it back first"
        lines.append(f"💳 Loan: you owe {loan['owed']} 🪙, {when}. /repay all")
    return "\n".join(lines)


def borrow(client, args):
    account = state.accounts[client.key]
    if time.time() - account.get("created", 0) < config.GIVE_MIN_AGE_HOURS * 3600:
        return client.say(f"💳 New accounts can't borrow in their first {config.GIVE_MIN_AGE_HOURS} hours.", "error")
    if account.get("messages", 0) < config.LOAN_MIN_MESSAGES:   # (extra accounts made just to borrow: no)
        return client.say(f"💳 Chat a bit first: you can borrow after {config.LOAN_MIN_MESSAGES} messages.", "error")
    if account["loan"]:
        return client.say(f"💳 You already have a loan: you owe {account['loan']['owed']} 🪙. /repay it first.", "error")
    text = args.strip()
    if not text.isdecimal() or int(text) <= 0:
        return client.say(f"💳 Use: /loan 200  (at most {config.LOAN_MAX})", "error")
    amount = int(text)
    if amount > config.LOAN_MAX:
        return client.say(f"💳 You can borrow at most {config.LOAN_MAX} 🪙.", "error")
    if amount > state.public_fund:   # loans only lend what the fund has: they never make new tokens
        return client.say(f"💳 The public fund can lend {state.public_fund} 🪙 right now.", "error")
    owed = amount + amount * config.LOAN_INTEREST_PERCENT // 100
    account["loan"] = {"owed": owed, "due": time.time() + config.LOAN_DAYS * 86400}
    state.public_fund -= amount
    account["tokens"] += amount
    storage.save_data()
    return client.say(f"💳 You borrowed {amount} 🪙. You owe {owed} 🪙 ({config.LOAN_INTEREST_PERCENT}% more) within "
                      f"{config.LOAN_DAYS} days. /repay all when you can.", "money")


def repay(client, args):
    account = state.accounts[client.key]
    loan = account["loan"]
    if not loan:
        return client.say("💳 You don't have a loan.", "error")
    amount = amount_of(client, args or "all", min(loan["owed"], account["tokens"]))
    if amount is None:
        return client.say("💳 Use: /repay 50  (or /repay all)", "error")
    amount = min(amount, loan["owed"])
    if amount > account["tokens"]:
        return client.say(f"💳 You only have {account['tokens']} 🪙.", "error")
    account["tokens"] -= amount
    pay_off(client.key, amount)
    if account["loan"] is None:
        return client.say("💳 You paid it all back. Thanks! 🙌", "money")
    return client.say(f"💳 You paid {amount} 🪙. You still owe {account['loan']['owed']} 🪙.", "money")


def pay_off(key, amount, save=True):
    """Tokens toward a loan go into the public fund."""
    account = state.accounts[key]
    owed = account["loan"]["owed"] - amount
    account["loan"] = None if owed <= 0 else {**account["loan"], "owed": owed}
    fund.collect(amount, "loan")
    if save:
        storage.save_data()


def collect_late(key):
    """At login: a late loan takes what it can from your wallet, then your savings."""
    account = state.accounts[key]
    loan = account.get("loan")
    if not loan or loan["due"] > time.time():
        return
    for place in ("tokens", "savings"):
        take = min(account.get(place, 0), (account["loan"] or {}).get("owed", 0))
        if take > 0:
            account[place] -= take
            pay_off(key, take, save=False)
    storage.save_data()
    rooms.tell(key, "💳 Your loan is late, so it took what it could from your tokens and savings."
               + ("" if account["loan"] is None else f" You still owe {account['loan']['owed']} 🪙."), "error")


def take_income(key, income):
    """The per-minute income of someone whose loan is late: it repays the loan first. Returns what's left."""
    loan = state.accounts[key].get("loan")
    if not loan or loan["due"] > time.time():
        return income
    paid = min(income, loan["owed"])
    pay_off(key, paid, save=False)   # (the income tick saves once at the end)
    if state.accounts[key]["loan"] is None:
        rooms.tell(key, "💳 Your late loan is paid back now. 🙌", "money")
    return income - paid


def pay_interest():
    """Once a day: savings earn interest, as long as the public fund has it."""
    for key, account in state.accounts.items():
        if account.get("savings", 0) <= 0:
            continue
        due = min(config.SAVINGS_INTEREST_MAX, account["savings"] * config.SAVINGS_INTEREST_PERCENT // 100)
        paid = min(state.public_fund, due, max(0, config.SAVINGS_MAX - account["savings"]))
        if paid > 0:
            state.public_fund -= paid
            account["savings"] += paid
            rooms.tell(key, f"🏦 Interest: +{paid} 🪙 in your savings.", "money")
