"""
📜 The cap table: who owns how much of a company, in basis points (10,000 = 100%), so it's always whole numbers.

Holders are strings: "p:adi" a player, "i:maya" an investor (the game's characters), "pool" the option pool.
Every function returns a NEW table and leaves the old one alone, and every table adds up to exactly TOTAL.
"""
from chatserver import config

TOTAL = 10_000
POOL = "pool"


def player(login):
    return "p:" + login


def investor(investor_id):
    return "i:" + investor_id


def normalize(cap):
    """Whole, positive numbers that add up to TOTAL: what rounding left over goes to the biggest holder."""
    cleaned = {holder: int(bp) for holder, bp in cap.items() if int(bp) > 0}
    if not cleaned:
        return {}
    biggest = max(cleaned, key=lambda holder: (cleaned[holder], holder))
    return {**cleaned, biggest: cleaned[biggest] + TOTAL - sum(cleaned.values())}


def dilute(cap, holder, bp):
    """A new owner of `bp` (new shares): everyone else shrinks by the same factor."""
    keep = (TOTAL - bp) / TOTAL
    shrunk = {h: int(v * keep) for h, v in cap.items()}
    return normalize({**shrunk, holder: shrunk.get(holder, 0) + bp})


def move(cap, giver, taker, bp):
    """Give `bp` from one holder to another (never more than the giver has)."""
    bp = max(0, min(bp, cap.get(giver, 0)))
    moved = {**cap, giver: cap.get(giver, 0) - bp, taker: cap.get(taker, 0) + bp}
    return normalize(moved)


def vested(grant, tick):
    """How much of a grant {"bp", "tick" (when it was given)} is really yours at this tick."""
    days = max(0, tick - grant["tick"])
    part = config.VEST_START_PERCENT / 100 + (1 - config.VEST_START_PERCENT / 100) * days / config.VEST_TICKS
    return int(grant["bp"] * min(1.0, part))


def share(cap, holder):
    return cap.get(holder, 0)


def percent_text(bp):
    """1250 -> "12.5%", 10000 -> "100%"."""
    text = f"{bp / 100:.1f}".rstrip("0").rstrip(".")
    return text + "%"
