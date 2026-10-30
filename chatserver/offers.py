"""
📎 File offers: nobody gets a file they didn't say yes to.

A client that said "offers" at login is asked first: it gets a normal notice
"📎 Dana wants to send you photo.jpg (2.3 MB).  /accept Dana  or  /decline Dana" with an extra optional field
"offer": {"id", "from", "filename", "size"} (the website draws Accept / Decline buttons from it).
The file goes through only after /accept. Offers expire after OFFER_SECONDS.
Old clients that never said "offers" get files straight away, like before.

Small files (one "file" packet) wait here in memory; big files (transfers.py) wait before their first chunk.
"""
import time

from chatserver import config, rooms, state, transfers


def wants_offers(key):
    client = state.online.get(key)
    return client is not None and "offers" in client.features


def size_text(size):
    """1536 -> "2 KB", 2_400_000 -> "2.3 MB"."""
    return f"{size / 1048576:.1f} MB" if size >= 1048576 else f"{max(1, -(-size // 1024))} KB"


def make(sender, target, filename, size, packet=None, transfer_key=None):
    """Ask `target` first. packet = a small file's {"type": "file"} packet; transfer_key = a waiting big file.
    Returns True if the offer was made (or tells the sender why not)."""
    waiting = [o for o in state.offers.values()]
    if any(o["from"] == sender for o in waiting):
        rooms.tell(sender, "📎 Wait until your last file is accepted or declined.", "error")
        return False
    if packet is not None and sum(len(o["packet"]["data"]) for o in waiting if o["packet"]) + len(packet["data"]) \
            > config.OFFERS_BYTES_MAX:   # all the small files waiting here together (they're kept in memory)
        rooms.tell(sender, "📎 Too many files are waiting on the server right now. Try again in a minute.", "error")
        return False
    if sum(1 for o in waiting if o["to"] == target) >= config.OFFERS_WAITING_MAX:
        rooms.tell(sender, f"📎 {rooms.nick(target)} already has {config.OFFERS_WAITING_MAX} files waiting. "
                           "Try again later.", "error")
        return False
    state.offer_count += 1
    offer = {"id": state.offer_count, "from": sender, "to": target, "filename": filename, "size": size,
             "time": time.time(), "packet": packet, "transfer": transfer_key}
    state.offers[offer["id"]] = offer
    name = rooms.nick(sender)
    rooms.tell(target, f"📎 {name} wants to send you {filename} ({size_text(size)}).  /accept file  or  /decline file",
               "event", offer={"id": offer["id"], "from": name, "filename": filename, "size": size})
    rooms.tell(sender, f"📨 Waiting for {rooms.nick(target)} to accept {filename}…")
    return True


def find(client, args):
    """The offer that /accept or /decline means, or None. args: "" (the newest), "file" (the newest),
    "file 7" (offer number 7, from the website's buttons) or a name (the newest from them)."""
    mine = sorted((o for o in state.offers.values() if o["to"] == client.key), key=lambda o: o["id"])
    words = args.split()
    if words[:1] == ["file"]:
        if len(words) > 1:
            return next((o for o in mine if str(o["id"]) == words[1]), None)
        return mine[-1] if mine else None
    if words:
        mine = [o for o in mine if rooms.nick(o["from"]).lower() == words[0].lower().lstrip("@")]
    return mine[-1] if mine else None


def is_file_answer(client, args):
    """Does this /accept or /decline mean a file? Yes for "file ..." (the website's buttons). Otherwise only if
    there's no game challenge it could mean: a waiting challenge always wins, so nobody can sneak a file in
    front of the game you meant to accept."""
    if args.split()[:1] == ["file"]:
        return True
    if find(client, args) is None:
        return False
    name = args.strip().lower().lstrip("@")
    return not any(time.time() - i["time"] < 180 and (not name or rooms.nick(i["from"]).lower() == name)
                   for i in state.invites.get(client.key, []))


def accept(client, args):
    offer = find(client, args)
    if offer is None:
        client.say("📭 No file offers waiting for you.", "error")
        return
    del state.offers[offer["id"]]
    if offer["packet"] is not None:
        client.send(offer["packet"])
        rooms.tell(offer["from"], f"📤 Sent {offer['filename']} ({size_text(offer['size'])}) to {rooms.shown(client.key)}.")
    elif not transfers.go_ahead(offer["transfer"]):
        client.say("📦 They cancelled that file.", "error")


def decline(client, args):
    offer = find(client, args)
    if offer is None:
        client.say("📭 No file offers waiting for you.", "error")
        return
    del state.offers[offer["id"]]
    client.say("👎 Declined.")
    refuse(offer, f"👎 {rooms.shown(client.key)} declined {offer['filename']}.")


def refuse(offer, why):
    """Tell the sender no (and stop a waiting big file)."""
    if offer["transfer"] is not None:
        transfers.cancel_waiting(offer["transfer"], why)
    else:
        rooms.tell(offer["from"], why, "error")


def expire(now=None):
    """Offers nobody answered in OFFER_SECONDS are dropped (checked every few seconds)."""
    now = time.time() if now is None else now
    for offer in list(state.offers.values()):
        if now - offer["time"] > config.OFFER_SECONDS:
            del state.offers[offer["id"]]
            refuse(offer, f"⌛ {rooms.nick(offer['to'])} didn't answer, so {offer['filename']} wasn't sent.")
            rooms.tell(offer["to"], f"⌛ The file offer from {rooms.nick(offer['from'])} expired.")


def forget_transfer(transfer_key):
    """A waiting big file was cancelled by its sender: the offer goes too."""
    for offer in list(state.offers.values()):
        if offer["transfer"] == transfer_key:
            del state.offers[offer["id"]]
            rooms.tell(offer["to"], f"📎 {rooms.nick(offer['from'])} cancelled {offer['filename']}.", "error")


def drop_all_of(key):
    """Someone left: their offers go (and the other side hears why)."""
    for offer in list(state.offers.values()):
        if key == offer["from"]:
            del state.offers[offer["id"]]
            rooms.tell(offer["to"], f"📎 {rooms.nick(key)} left, so their file offer is gone.", "error")
        elif key == offer["to"]:
            del state.offers[offer["id"]]
            refuse(offer, f"📎 {rooms.nick(key)} left before accepting {offer['filename']}.")
