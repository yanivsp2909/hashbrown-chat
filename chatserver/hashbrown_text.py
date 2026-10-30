"""
🧽 Text helpers for Hashbrown: the safety net for its answers and the time in Israel.
Both are pure functions (no server state), so they are easy to test.
"""
import re
from datetime import date, datetime, timedelta, timezone

from chatserver import config

CUT_NOTE = "…(cut: Hashbrown only writes small code)"

# ``` ... ``` (a block that never closes counts as code until the end)
CODE_BLOCK = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
DASH = r"(?:—|–|--+)"                                    # em dash, en dash, "--"
LINE_START_MARK = re.compile(rf"^[ \t]*(?:[-*•][ \t]+|{DASH}[ \t]*)", re.MULTILINE)  # bullets, a dash starting a line
LINE_END_DASH = re.compile(rf"[ \t]*{DASH}[ \t]*(?=\n|\Z)")                           # a dash ending a line
SPACED_DASH = re.compile(rf"[ \t]+{DASH}[ \t]+")      # "a — b" -> "a, b"
TIGHT_DASH = re.compile(DASH)                           # "5–10" -> "5-10"
HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
BOLD = re.compile(r"\*\*|__")
MANY_NEWLINES = re.compile(r"\n{3,}")


# ---------------------------------------------------------------- the safety net for answers

def clean_answer(text):
    """Make an answer follow the house style even if the AI forgot the rules: plain text, no dashes
    like — or --, no markdown, short. Code blocks (``` lines) are kept as they are, except that
    too-long ones are cut. Never raises; returns "" if nothing is left."""
    if not isinstance(text, str):
        return ""
    pieces = []
    budget = config.HASHBROWN_MAX_CHARS    # characters left for the non-code text
    position = 0
    for block in CODE_BLOCK.finditer(text):
        plain, cut = _take_text(text[position:block.start()], budget)
        pieces.append(plain)
        if cut:
            return "".join(pieces).strip()
        budget -= len(plain)
        pieces.append(_shorten_code(block.group()))
        position = block.end()
    plain, _ = _take_text(text[position:], budget)
    pieces.append(plain)
    return "".join(pieces).strip()


def _take_text(text, budget):
    """Clean plain text and keep at most `budget` characters. Returns (text, was_cut)."""
    text = _clean_plain(text)
    if len(text) <= budget:
        return text, False
    kept = text[:budget]
    if not text[budget].isspace():     # we're inside a word: back up to the end of the one before
        words = kept.rsplit(None, 1)
        if len(words) == 2:
            kept = words[0]
    return kept.rstrip(" ,;:-\n") + "…", True


def _clean_plain(text):
    text = BOLD.sub("", text)
    text = HEADING.sub("", text)
    text = LINE_START_MARK.sub("", text)
    text = LINE_END_DASH.sub("", text)
    text = SPACED_DASH.sub(", ", text)
    text = TIGHT_DASH.sub("-", text)
    return MANY_NEWLINES.sub("\n\n", text)


def _shorten_code(block):
    """Cut a code block to HASHBROWN_MAX_CODE_LINES lines of code, with a note after it."""
    lines = block.split("\n")
    if len(lines) < 3:
        return block
    closed = lines[-1].strip() == "```"
    body = lines[1:-1] if closed else lines[1:]
    if len(body) <= config.HASHBROWN_MAX_CODE_LINES:
        return block
    kept = [lines[0]] + body[:config.HASHBROWN_MAX_CODE_LINES] + (["```"] if closed else [])
    return "\n".join(kept) + "\n" + CUT_NOTE


# ---------------------------------------------------------------- time in Israel

_zone_looked_up = False
_zone = None


def _israel_zone():
    """The Asia/Jerusalem time zone, or None (Python 3.8 has no zoneinfo, and some systems have no tz data)."""
    global _zone_looked_up, _zone
    if not _zone_looked_up:
        _zone_looked_up = True
        try:
            from zoneinfo import ZoneInfo
            _zone = ZoneInfo("Asia/Jerusalem")
        except (ImportError, KeyError, OSError):
            _zone = None
    return _zone


def _last_sunday(year, month):
    """March and October both have 31 days."""
    last = date(year, month, 31)
    return last - timedelta(days=(last.weekday() + 1) % 7)   # Monday is 0, Sunday is 6


def israel_now_fallback(utc_now):
    """Israel time from UTC without any tz database. Summer time (UTC+3) runs from the Friday
    before the last Sunday of March (02:00) to the last Sunday of October (02:00), otherwise UTC+2."""
    utc_now = utc_now.astimezone(timezone.utc)
    start_day = _last_sunday(utc_now.year, 3) - timedelta(days=2)
    end_day = _last_sunday(utc_now.year, 10)
    start = datetime(start_day.year, start_day.month, start_day.day, 0, tzinfo=timezone.utc)   # 02:00 at UTC+2
    end = datetime(end_day.year, end_day.month, end_day.day, 2, tzinfo=timezone.utc) - timedelta(hours=3)  # 02:00 at UTC+3
    hours = 3 if start <= utc_now < end else 2
    return (utc_now + timedelta(hours=hours)).replace(tzinfo=None)


def israel_now(utc_now=None):
    """The current time in Israel as a plain (naive) datetime."""
    utc_now = utc_now or datetime.now(timezone.utc)
    zone = _israel_zone()
    if zone is None:
        return israel_now_fallback(utc_now)
    return utc_now.astimezone(zone).replace(tzinfo=None)


def israel_time_text(utc_now=None):
    """Like 'Wednesday 2026-07-15 13:05'."""
    return israel_now(utc_now).strftime("%A %Y-%m-%d %H:%M")
