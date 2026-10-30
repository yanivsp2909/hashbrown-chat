"""
🏦 Savings and 💳 loan commands (the rules are in savings.py).
"""
from chatserver import registry, savings


@registry.command("/save", "/save amount", "put tokens in savings (interest every day) 🏦", "🏦 Savings & loans")
def cmd_save(client, args):
    savings.save(client, args)


@registry.command("/withdraw", "/withdraw amount", "take tokens out of savings", "🏦 Savings & loans")
def cmd_withdraw(client, args):
    savings.withdraw(client, args)


@registry.command("/savings", "/savings", "your savings and loan", "🏦 Savings & loans")
def cmd_savings(client, args):
    client.say(savings.status_text(client.key), "money")


@registry.command("/loan", "/loan amount", "borrow tokens (you pay back a bit more) 💳", "🏦 Savings & loans")
def cmd_loan(client, args):
    savings.borrow(client, args)


@registry.command("/repay", "/repay [amount|all]", "pay your loan back", "🏦 Savings & loans")
def cmd_repay(client, args):
    savings.repay(client, args)
