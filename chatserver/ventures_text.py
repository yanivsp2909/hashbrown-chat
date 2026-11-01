"""
🏢 How Hashbrown Ventures writes its numbers: $12.3K, $4.5M, $1.2B, and the daily report.
(Plain functions: no state, so the simulation and the tests can use them.)
"""
from chatserver import config


def money(dollars):
    """$950, $12.3K, $4.5M, $1.2B (negative: -$12.3K)."""
    sign, value = ("-" if dollars < 0 else ""), abs(dollars)
    for size, letter in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if round(value / size, 1) >= 1:   # (rounded first, so $999,960 is $1M and not $1000K)
            text = f"{value / size:.1f}".rstrip("0").rstrip(".")
            return f"{sign}${text}{letter}"
    return f"{sign}${int(round(value))}"


def whole(number):
    """1234.6 -> "1,235"."""
    return f"{int(round(number)):,}"


def stage_name(stage):
    return config.STAGE_NAMES[stage]


def sector_title(sector):
    info = config.SECTORS[sector]
    return f"{info['icon']} {info['name']}"


def runway_text(days):
    return "∞ (profitable)" if days is None else f"{days} days"


def change(old, new):
    """"+6%" / "-3%" / "" for a number that moved."""
    if not old:
        return ""
    percent = (new - old) / old * 100
    return f" ({percent:+.0f}%)" if abs(percent) >= 0.5 else ""


def report_lines(old, new, numbers):
    """The daily report. numbers: {"tick", "revenue", "old_revenue", "burn", "runway", "new", "lost"}."""
    sector = config.SECTORS[new["sector"]]
    churn = numbers["lost"] / old["customers"] * 100 if old["customers"] else 0
    lines = [f"📊 Day {numbers['tick']} · {new['name']} ({sector_title(new['sector'])}, {stage_name(new['stage'])})",
             f"💵 Cash {money(new['cash'])} ({money(new['cash'] - old['cash'])}) · 🔥 burn {money(numbers['burn'])}/day · "
             f"📈 MRR {money(numbers['revenue'])}{change(numbers['old_revenue'], numbers['revenue'])} · "
             f"⏳ runway {runway_text(numbers['runway'])}",
             f"👥 {whole(new['customers'])} {sector['customers']} (+{whole(numbers['new'])}, churn {churn:.1f}%) · "
             f"⭐ quality {new['quality']:.0f} · 📣 hype {new['hype']:.0f} · 🤝 reputation {new['reputation']:.0f} · "
             f"💎 {money(new['valuation'])}"]
    return lines
