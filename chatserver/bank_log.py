"""
🏦 The history of every group bank, saved in history.db (table bank_log), for the website's Bank view:
donations, upgrades bought, war prizes, Hashbrown questions paid by the bank (and their refunds), and one
balance snapshot an hour for the chart. The minute-by-minute income isn't a row (the snapshots show it).
"""
import time

from chatserver import config, history, state

SHOWN_KINDS = ("donate", "upgrade", "war_won", "war_lost", "hashbrown", "refund")


def record(group_key, kind, who, amount, note=""):
    """One change of the bank. Call it right after the bank changed (the row keeps the balance after it)."""
    balance = state.groups[group_key]["bank"] if group_key in state.groups else 0

    def write(connection):
        connection.execute("INSERT INTO bank_log (grp, time, kind, who, amount, note, balance) VALUES (?,?,?,?,?,?,?)",
                           (group_key, time.time(), kind, who, amount, note, balance))
        connection.commit()
    history.run(write)


def recent(group_key, limit=None):
    """Newest first: [{time, kind, who (shown name), amount, note, balance}]."""
    marks = ", ".join("?" * len(SHOWN_KINDS))
    rows = history.run(lambda c: c.execute(
        f"SELECT time, kind, who, amount, note, balance FROM bank_log WHERE grp = ? AND kind IN ({marks}) "
        "ORDER BY id DESC LIMIT ?", (group_key, *SHOWN_KINDS, limit or config.BANK_HISTORY_SHOWN)).fetchall(), [])
    return [{"time": t, "kind": k, "who": name_of(who), "amount": a, "note": n, "balance": b}
            for t, k, who, a, n, b in rows]


def top_donors(group_key, limit=5):
    rows = history.run(lambda c: c.execute(
        "SELECT who, SUM(amount) AS total FROM bank_log WHERE grp = ? AND kind = 'donate' "
        "GROUP BY who ORDER BY total DESC, MIN(id) LIMIT ?", (group_key, limit)).fetchall(), [])
    return [{"name": name_of(who), "amount": total} for who, total in rows]


def chart(group_key, days=None):
    """[{time, balance}] oldest first: the hourly snapshots of the last BANK_CHART_DAYS, then the balance now.
    (Only snapshots, never one point per donation: 1-token donations can't make the packet huge.)"""
    since = time.time() - (days or config.BANK_CHART_DAYS) * 86400
    rows = history.run(lambda c: c.execute(
        "SELECT time, balance FROM bank_log WHERE grp = ? AND kind = 'snapshot' AND time >= ? ORDER BY id DESC LIMIT ?",
        (group_key, since, config.BANK_CHART_POINTS)).fetchall(), [])
    points = [{"time": t, "balance": b} for t, b in reversed(rows)]
    if group_key in state.groups:
        now = int(time.time()) // 60 * 60   # (to the minute, so an unchanged screen isn't sent again)
        points.append({"time": now, "balance": state.groups[group_key]["bank"]})
    return points


def snapshot_all(now=None):
    """Once an hour at most, each group's balance becomes a chart point (called every minute)."""
    now = time.time() if now is None else now
    for key in list(state.groups):
        if now - state.bank_snapshots.get(key, 0) >= 3600:
            state.bank_snapshots[key] = now
            record(key, "snapshot", "", 0)
            prune(now)


def prune(now):
    """Rows older than BANK_LOG_KEEP_DAYS go (the screen shows the last 30 rows and 7 days anyway)."""
    def drop(connection):
        connection.execute("DELETE FROM bank_log WHERE time < ?", (now - config.BANK_LOG_KEEP_DAYS * 86400,))
        connection.commit()
    history.run(drop)


def forget(group_key):
    """A disbanded group's history goes with it (a new group with the same name starts empty)."""
    state.bank_snapshots.pop(group_key, None)

    def wipe(connection):
        connection.execute("DELETE FROM bank_log WHERE grp = ?", (group_key,))
        connection.commit()
    history.run(wipe)


def name_of(login):
    """A login as people see it today (they may have renamed themselves since)."""
    return state.accounts[login]["nick"] if login in state.accounts else login
