"""
🛒 The player marketplace: sell your badges to other players.
/sell badge 🔥 300 lists one (it leaves your badges while it's listed), /market shows the listings,
/market buy N buys listing N (MARKETPLACE_FEE_PERCENT goes to the public fund, the rest to the seller),
/market cancel N takes yours back. Saved in chat_data.json ("economy" -> "extra" -> "listings").
"""
import time

from chatserver import config, fund, rooms, state, storage


def listings():
    return state.economy_extra.get("listings", [])


def set_listings(rows):
    state.economy_extra = {**state.economy_extra, "listings": rows}


def sell(client, args):
    """/sell badge 🔥 300"""
    parts = args.split()
    if len(parts) != 3 or parts[0].lower() != "badge" or not parts[2].isdecimal() or not 0 < int(parts[2]) <= config.MARKETPLACE_MAX_PRICE:
        return client.say(f"🛒 Use: /sell badge 🔥 300  (a price from 1 to {config.MARKETPLACE_MAX_PRICE})", "error")
    badge, price = parts[1], int(parts[2])
    account = state.accounts[client.key]
    if badge not in account["badges"]:
        return client.say(f"🛒 You don't own {badge}. Yours: {' '.join(account['badges']) or 'none'}", "error")
    if sum(1 for row in listings() if row["seller"] == client.key) >= config.MARKETPLACE_LISTINGS_MAX:
        return client.say(f"🛒 You can have at most {config.MARKETPLACE_LISTINGS_MAX} things for sale.", "error")
    account["badges"] = [b for b in account["badges"] if b != badge]
    if account["badge"] == badge:
        account["badge"] = ""
    state.economy_extra = {**state.economy_extra, "next_listing": state.economy_extra.get("next_listing", 0) + 1}
    row = {"id": state.economy_extra["next_listing"], "seller": client.key, "badge": badge, "price": price, "time": time.time()}
    set_listings(listings() + [row])
    storage.save_data()
    return client.say(f"🛒 You listed {badge} for {price} 🪙 (number {row['id']}). /market cancel {row['id']} takes it back.", "money")


def show(client):
    rows = listings()
    if not rows:
        return client.say("🛒 Marketplace: nothing for sale. Sell a badge: /sell badge 🔥 300", "money")
    lines = ["🛒 Marketplace (/market buy N):"] + [
        f"  {row['id']}.  {row['badge']}  {row['price']} 🪙  from {rooms.nick(row['seller']) if row['seller'] in state.accounts else '?'}"
        for row in rows]
    lines.append(f"  A {config.MARKETPLACE_FEE_PERCENT}% fee goes to the public fund.")
    return client.say("\n".join(lines), "money")


def find(client, text):
    row = next((r for r in listings() if text.isdecimal() and r["id"] == int(text)), None)
    if row is None:
        client.say(f"🛒 No listing number {text[:8]}. See /market", "error")
    return row


def buy(client, text):
    row = find(client, text)
    if row is None:
        return None
    account = state.accounts[client.key]
    if row["seller"] == client.key:
        return client.say("🛒 That's your own. /market cancel takes it back.", "error")
    if row["badge"] in account["badges"]:
        return client.say(f"🛒 You already have {row['badge']}.", "error")
    if account["tokens"] < row["price"]:
        return client.say(f"💸 It costs {row['price']} 🪙, you have {account['tokens']}.", "error")
    charge = row["price"] * config.MARKETPLACE_FEE_PERCENT // 100
    account["tokens"] -= row["price"]
    account["badges"] = account["badges"] + [row["badge"]]
    if row["seller"] in state.accounts:
        state.accounts[row["seller"]]["tokens"] += row["price"] - charge
    fund.collect(charge, "marketplace fee")
    set_listings([r for r in listings() if r["id"] != row["id"]])
    storage.save_data()
    rooms.tell(row["seller"], f"🛒 {rooms.shown(client.key)} bought your {row['badge']}: you sold {row['badge']} for "
                              f"{row['price']} 🪙 (+{row['price'] - charge} 🪙 after the fee).", "money")
    return client.say(f"🛒 You bought {row['badge']} for {row['price']} 🪙. Wear it: /badge {row['badge']}", "money")


def cancel(client, text):
    row = find(client, text)
    if row is None:
        return None
    if row["seller"] != client.key:
        return client.say("🛒 That's not yours.", "error")
    account = state.accounts[client.key]
    account["badges"] = account["badges"] + [row["badge"]]
    set_listings([r for r in listings() if r["id"] != row["id"]])
    storage.save_data()
    return client.say(f"🛒 {row['badge']} is back with you.", "money")
