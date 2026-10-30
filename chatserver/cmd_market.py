"""
📈 Market commands: /stocks, /buy SYM n (and /buy 🔥 still buys badges), /sell SYM n, /portfolio.
"""
from chatserver import auctions, market, marketplace, registry, storage


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


@registry.command("/sell", "/sell FRY 5", "sell shares (or a badge: /sell badge 🔥 300)", "📈 Market")
def cmd_sell(client, args):
    if args.split()[:1] and args.split()[0].lower() == "badge":   # 🛒 the player marketplace
        marketplace.sell(client, args)
        return
    found = parse_trade(client, args, "sell")
    if found:
        error = market.trade(client, *found, buying=False)
        if error:
            client.say(error, "error")
        storage.save_data()


@registry.command("/portfolio", "/portfolio", "your shares and what they're worth", "📈 Market")
def cmd_portfolio(client, args):
    client.say(market.portfolio_text(client.key), "money")


@registry.command("/market", "/market [buy N | cancel N]", "players' badges for sale 🛒", "📈 Market")
def cmd_market(client, args):
    word, _, rest = args.strip().partition(" ")
    if word.lower() == "buy":
        marketplace.buy(client, rest.strip())
    elif word.lower() == "cancel":
        marketplace.cancel(client, rest.strip())
    else:
        marketplace.show(client)


@registry.command("/bid", "/bid amount", "bid in the lobby's auction 🔨", "📈 Market")
def cmd_bid(client, args):
    auctions.bid(client, args)


@registry.command("/auction", "/auction", "admin: start an auction of a rare badge now", "🛠️ Admin")
def cmd_auction(client, args):
    from chatserver import state
    if not state.accounts[client.key]["admin"]:
        client.say("🔨 Only server admins can start an auction.", "error")
    elif not auctions.start():
        client.say("🔨 An auction is already on.", "error")
