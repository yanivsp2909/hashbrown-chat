"""
✓✓ Read receipts for private messages (/send to someone online).

    sender's copy:   the usual 💌 notice + "pm": {"id": 7, "status": "sent"}
    receiver's copy: the usual 💌 notice + "pm_id": 7
    server -> sender {"type": "receipt", "id": 7, "status": "delivered"}   once it really went out to them
    receiver -> server {"type": "seen", "id": 7}                          their app shows it (the website does)
    server -> sender {"type": "receipt", "id": 7, "status": "seen"}

Old clients ignore the extra fields and the new packets. Messages kept for someone offline have no receipts.
"""
from chatserver import config, state


def new_pm(sender, target):
    """A number for this private message; only the last RECEIPTS_KEEP are remembered."""
    state.pm_count += 1
    state.pms[state.pm_count] = {"from": sender, "to": target}
    while len(state.pms) > config.RECEIPTS_KEEP:
        del state.pms[next(iter(state.pms))]   # the oldest (dicts keep the order things were added)
    return state.pm_count


def tell_sender(pm_id, status):
    pm = state.pms.get(pm_id)
    sender = state.online.get(pm["from"]) if pm else None
    if sender is not None:
        sender.send({"type": "receipt", "id": pm_id, "status": status})


def delivered(pm_id):
    """Runs in the receiver's writer thread once the message has really been sent to them."""
    with state.lock:
        tell_sender(pm_id, "delivered")


def seen(client, msg):
    """{"type": "seen", "id"}: only the receiver may say it, and only once."""
    pm_id = msg.get("id")
    pm = state.pms.get(pm_id) if isinstance(pm_id, int) and not isinstance(pm_id, bool) else None
    if pm is None or pm["to"] != client.key:
        return
    tell_sender(pm_id, "seen")
    del state.pms[pm_id]
