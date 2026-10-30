"""
📈 Market commands: /stocks, /buy SYM n (and /buy 🔥 still buys badges), /sell SYM n, /portfolio.
"""
from chatserver import market, registry, storage


def parse_trade(client, args, verb):
    """'FRY 5' -> ("FRY", 5), or None (and says how)."""
    parts = args.split()
    if len(parts) != 2 or not parts[1].isdecimal() or not 0 < int(parts[1]) <= 100000:
        client.say(f"📈 Use: /{verb} FRY 5  (see /stocks)", "error")
        return None
    sym = market.symbol(parts[0])
    if sym is None:
        client.say(f"📈 No stock called {parts[0][:12]}. See /stocks", "error")
        return None
    return sym, int(parts[1])


def buy_stock(client, args):
    """/buy FRY 5 (cmd_tokens.cmd_buy sends stock symbols here)."""
    found = parse_trade(client, args, "buy")
    if found:
        error = market.trade(client, *found, buying=True)
        if error:
            client.say(error, "error")
        storage.save_data()


@registry.command("/stocks", "/stocks", "stock prices 📈 (/buy FRY 5, /sell FRY 5)", "📈 Market")
def cmd_stocks(client, args):
    market.ensure()
    client.say(market.listing(), "money")


@registry.command("/sell", "/sell FRY 5", "sell shares", "📈 Market")
def cmd_sell(client, args):
    found = parse_trade(client, args, "sell")
    if found:
        error = market.trade(client, *found, buying=False)
        if error:
            client.say(error, "error")
        storage.save_data()


@registry.command("/portfolio", "/portfolio", "your shares and what they're worth", "📈 Market")
def cmd_portfolio(client, args):
    client.say(market.portfolio_text(client.key), "money")
