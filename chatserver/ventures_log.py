"""
🏢 Hashbrown Ventures' history in history.db (it only grows, nothing is deleted):
venture_days, one row per company per tick for the HQ charts, and venture_offers, every term sheet with the AI's
raw answer and what became of it. (The live company records are in chat_data.json: see ventures_store.py.)
"""
import json
import time

from chatserver import config, history, ventures_sim


def record_day(co):
    """The company's numbers after a tick. INSERT OR REPLACE: a tick that runs again just writes the same row."""
    row = (co["id"], co["age"], time.time(), co["cash"], co["revenue"], co["customers"], co["quality"], co["hype"],
           co["reputation"], co["valuation"], ventures_sim.staff_total(co))

    def write(connection):
        connection.execute("INSERT OR REPLACE INTO venture_days (company, age, time, cash, revenue, customers, quality, "
                           "hype, reputation, valuation, staff) VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        connection.commit()
    history.run(write)


def days(cid, limit=None):
    """Oldest first: [{age, cash, revenue, customers, quality, hype, reputation, valuation, staff}]."""
    rows = history.run(lambda c: c.execute(
        "SELECT age, cash, revenue, customers, quality, hype, reputation, valuation, staff FROM venture_days "
        "WHERE company = ? ORDER BY age DESC LIMIT ?", (cid, limit or config.VENTURES_CHART_TICKS)).fetchall(), [])
    names = ("age", "cash", "revenue", "customers", "quality", "hype", "reputation", "valuation", "staff")
    return [dict(zip(names, r)) for r in reversed(rows)]


def record_offer(sheet, status, raw=None):
    """A term sheet and what happened to it (offered / accepted / declined / countered / expired / walked)."""
    row = (sheet["id"], sheet["company"], time.time(), sheet["investor"], sheet["stage"], sheet["amount"],
           sheet["post"], sheet["bp"], status, sheet.get("source", ""), json.dumps(raw, ensure_ascii=False)[:4000])

    def write(connection):
        connection.execute("INSERT OR REPLACE INTO venture_offers (id, company, time, investor, stage, amount, post, bp, "
                           "status, source, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
        connection.commit()
    history.run(write)
