"""
📰 Hashbrown's market news: when a company's price is MARKET_NEWS_MOVE_PERCENT or more up or down from the day's
open, Hashbrown posts one funny line in the Lobby. Once per stock per day, at most MARKET_NEWS_PER_DAY a day, and
each one counts toward the server-wide Hashbrown cap (the server pays). Without Hashbrown, no news.
"""
from chatserver import config, hashbrown_extras, history, market, rooms, state, textutil


def check(old, new):
    """After every market tick (market.on_tick)."""
    today = textutil.today()
    told = state.economy_extra.get("news", {})
    if told.get("day") != today:
        told = {"day": today, "stocks": []}
    for sym, (icon, name, _) in config.STOCKS.items():
        stock = state.stocks.get(sym)
        if not stock or not stock["open"] or sym in told["stocks"] or len(told["stocks"]) >= config.MARKET_NEWS_PER_DAY:
            continue
        change = (stock["price"] - stock["open"]) * 100 / stock["open"]
        if abs(change) < config.MARKET_NEWS_MOVE_PERCENT or not hashbrown_extras.take_server_question():
            continue
        told = {**told, "stocks": told["stocks"] + [sym]}
        way = "up" if change > 0 else "down"
        task = (f"You're the friend group's funny market reporter. {icon} {sym} ({name}) is {way} {abs(change):.0f}% "
                f"today, now {stock['price']} tokens (fake money in a chat game). Write ONE short funny news line "
                "about it, like a headline. No advice.")
        hashbrown_extras.ask_in_background(task, post)
    state.economy_extra = {**state.economy_extra, "news": told}


def post(answer):
    msg = rooms.chat_message("Hashbrown", "🥔", f"📰 {answer}")
    history.add("lobby", msg)
    rooms.send_room("lobby", msg)


market.on_tick(check)
