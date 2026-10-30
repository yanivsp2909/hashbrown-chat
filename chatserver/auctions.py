"""
🔨 Auctions: a rare badge (config.RARE_BADGES, not in the shop) is auctioned in the Lobby, every
AUCTION_EVERY_HOURS while at least two people are online (or when an admin types /auction).
/bid N: at least AUCTION_START_PRICE, and AUCTION_MIN_STEP more than the top bid. Your tokens are held (taken
now) and given back when someone bids more. When AUCTION_SECONDS are up the top bid wins the badge, and the
money goes to the public fund (tokens leave circulation into the fund instead of piling up).
Saved in chat_data.json, so a held bid is given back after a restart.
"""
import random
import time

from chatserver import config, fund, rooms, state, storage


def current():
    return state.economy_extra.get("auction")


def set_current(auction):
    extra = {k: v for k, v in state.economy_extra.items() if k != "auction"}
    state.economy_extra = {**extra, "auction": auction} if auction else extra


def start(badge=None):
    if current():
        return False
    badge = badge or random.choice(config.RARE_BADGES)
    set_current({"badge": badge, "until": time.time() + config.AUCTION_SECONDS, "bid": 0, "by": None})
    state.economy_extra = {**state.economy_extra, "last_auction": time.time()}
    rooms.announce(f"🔨 Auction in the lobby: the rare badge {badge}! Bid with /bid {config.AUCTION_START_PRICE} or more. "
                   f"{config.AUCTION_SECONDS // 60} minutes. The money goes to the public fund.")
    return True


def bid(client, args):
    auction = current()
    if not auction:
        return client.say("🔨 No auction right now. One starts in the lobby every few hours.", "error")
    text = args.strip()
    lowest = max(config.AUCTION_START_PRICE, auction["bid"] + config.AUCTION_MIN_STEP if auction["by"] else 0)
    if not text.isdecimal() or int(text) < lowest:
        return client.say(f"🔨 Bid at least {lowest} 🪙: /bid {lowest}", "error")
    amount = int(text)
    account = state.accounts[client.key]
    if auction["badge"] in account["badges"]:
        return client.say(f"🔨 You already have {auction['badge']}.", "error")
    if auction["by"] == client.key:
        return client.say("🔨 You're already the top bid.", "error")
    if account["tokens"] < amount:
        return client.say(f"💸 You only have {account['tokens']} 🪙.", "error")
    if auction["by"] in state.accounts:   # the one before gets their tokens back
        state.accounts[auction["by"]]["tokens"] += auction["bid"]
        rooms.tell(auction["by"], f"🔨 You were outbid on {auction['badge']}: {amount} 🪙. Your {auction['bid']} 🪙 are back.", "error")
    account["tokens"] -= amount
    set_current({**auction, "bid": amount, "by": client.key})
    storage.save_data()
    rooms.notify_room("lobby", f"🔨 {rooms.shown(client.key)} is the top bid for {auction['badge']}: {amount} 🪙", kind="money")
    return client.say(f"🔨 You're the top bid: {amount} 🪙 (held until the end).", "money")


def tick():
    """Every minute: an auction that's over ends; a new one starts every AUCTION_EVERY_HOURS with 2+ online."""
    auction = current()
    now = time.time()
    if auction and now >= auction["until"]:
        set_current(None)
        if auction["by"] in state.accounts:
            winner = state.accounts[auction["by"]]
            winner["badges"] = winner["badges"] + [auction["badge"]]
            fund.collect(auction["bid"], "auction")
            rooms.announce(f"🔨 {rooms.shown(auction['by'])} won the auction: {auction['badge']} for {auction['bid']} 🪙!", "money")
        else:
            rooms.announce(f"🔨 Nobody bid on {auction['badge']}. Next time!")
        storage.save_data()
    elif not auction and len(state.online) >= 2 and now - state.economy_extra.get("last_auction", 0) >= config.AUCTION_EVERY_HOURS * 3600:
        start()


def refund_after_restart():
    """A server that restarted mid-auction: the held bid goes back, the auction is off."""
    auction = current()
    if auction:
        if auction["by"] in state.accounts:
            state.accounts[auction["by"]]["tokens"] += auction["bid"]
        set_current(None)
