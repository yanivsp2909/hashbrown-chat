"""clean_answer (the regex safety net) and Israel time. Pure functions: no sockets, no fake AI."""
from datetime import datetime, timezone

import pytest

from chatserver import config, hashbrown_text
from chatserver.hashbrown_text import clean_answer, israel_now, israel_now_fallback

pytestmark = pytest.mark.unit

NOTE = "…(cut: Hashbrown only writes small code)"


# ---------------------------------------------------------------- dashes

@pytest.mark.parametrize("raw, clean", [
    ("hello — world", "hello, world"),
    ("hello – world", "hello, world"),
    ("hello -- world", "hello, world"),
    ("hello --- world", "hello, world"),
    ("5–10 minutes", "5-10 minutes"),
    ("well—maybe", "well-maybe"),
    ("a--b", "a-b"),
    ("— starts here", "starts here"),
    ("a well-known fact - really", "a well-known fact - really"),   # plain hyphens stay
])
def test_dashes(raw, clean):
    assert clean_answer(raw) == clean


def test_hebrew_dashes_and_text_stay_hebrew():
    assert clean_answer("שלום — מה קורה? כיף -- אחי") == "שלום, מה קורה? כיף, אחי"


# ---------------------------------------------------------------- markdown

def test_bold_markers_are_removed():
    assert clean_answer("this is **very** __good__") == "this is very good"


def test_heading_markers_are_removed():
    assert clean_answer("# Title\n## Sub title\ntext") == "Title\nSub title\ntext"


def test_a_hash_inside_a_line_is_kept():
    assert clean_answer("use #1 please") == "use #1 please"


@pytest.mark.parametrize("bullet", ["- ", "* ", "• "])
def test_bullets_at_line_starts_are_removed(bullet):
    assert clean_answer(f"{bullet}one\n{bullet}two") == "one\ntwo"


def test_a_bullet_marker_inside_a_line_is_kept():
    assert clean_answer("ten - five = five") == "ten - five = five"


def test_three_or_more_newlines_collapse():
    assert clean_answer("a\n\n\n\nb") == "a\n\nb"


def test_a_double_newline_is_kept():
    assert clean_answer("a\n\nb") == "a\n\nb"


def test_plain_text_and_emojis_are_unchanged():
    assert clean_answer("Hey! 😄 all good") == "Hey! 😄 all good"


def test_empty_and_whitespace_give_empty():
    assert clean_answer("") == ""
    assert clean_answer("  \n ") == ""


def test_not_a_string_gives_empty():
    assert clean_answer(None) == ""


# ---------------------------------------------------------------- code blocks

def test_code_blocks_are_left_untouched():
    code = "```python\nx = 5 -- 3\n# comment — here\n- item **bold**\n```"
    assert clean_answer(f"look — here:\n{code}\nnice -- one") == f"look, here:\n{code}\nnice, one"


def test_dashes_inside_code_stay():
    code = "```\na--b — c\n```"
    assert clean_answer(code) == code


def test_a_code_block_over_the_limit_is_cut_with_a_note(monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_MAX_CODE_LINES", 3)
    code = "```py\n" + "\n".join(f"line{i}" for i in range(10)) + "\n```"
    assert clean_answer(code) == "```py\nline0\nline1\nline2\n```\n" + NOTE


def test_a_code_block_exactly_at_the_limit_is_kept(monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_MAX_CODE_LINES", 3)
    code = "```\na\nb\nc\n```"
    assert clean_answer(code) == code


def test_default_code_limit_is_50_lines():
    body = "\n".join(f"x{i}" for i in range(60))
    out = clean_answer(f"```\n{body}\n```")
    assert "x49" in out and "x50" not in out and NOTE in out


def test_an_unclosed_code_block_is_treated_as_code(monkeypatch):
    out = clean_answer("hi\n```\na -- b")
    assert out == "hi\n```\na -- b"


def test_several_code_blocks_each_get_cut(monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_MAX_CODE_LINES", 1)
    out = clean_answer("```\na\nb\n```\ntext\n```\nc\nd\n```")
    assert out.count(NOTE) == 2


def test_code_does_not_count_toward_the_character_limit(monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_MAX_CHARS", 20)
    code = "```\n" + "x" * 200 + "\n```"
    assert clean_answer(f"short\n{code}") == f"short\n{code}"


# ---------------------------------------------------------------- length

def test_long_text_is_cut_at_a_word_boundary(monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_MAX_CHARS", 20)
    out = clean_answer("one two three four five six seven")
    assert out == "one two three four…"


def test_text_exactly_at_the_limit_is_kept(monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_MAX_CHARS", 9)
    assert clean_answer("one two 3") == "one two 3"


def test_one_long_word_is_cut_hard(monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_MAX_CHARS", 5)
    assert clean_answer("abcdefghij") == "abcde…"


def test_hebrew_is_cut_at_a_word_boundary(monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_MAX_CHARS", 12)
    assert clean_answer("שלום לכולם מה קורה היום") == "שלום לכולם…"


def test_the_default_limit_is_700():
    out = clean_answer("word " * 400)
    assert len(out) <= config.HASHBROWN_MAX_CHARS + 1
    assert out.endswith("…")


def test_text_after_a_cut_is_dropped(monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_MAX_CHARS", 8)
    out = clean_answer("aaaa bbbb cccc\n```\ncode\n```\nmore text")
    assert out == "aaaa…"


# ---------------------------------------------------------------- Israel time

def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


@pytest.mark.parametrize("when, expected_hour", [
    (utc(2026, 1, 15, 10, 0), 12),    # winter: UTC+2
    (utc(2026, 7, 15, 10, 0), 13),    # summer: UTC+3
    (utc(2026, 3, 26, 23, 59), 1),    # Thursday before the switch: still +2 (-> Friday 01:59)
    (utc(2026, 3, 27, 0, 0), 3),      # Friday 02:00 local: summer time starts (-> 03:00)
    (utc(2026, 10, 24, 22, 59), 1),   # Saturday night: still +3 (-> Sunday 01:59)
    (utc(2026, 10, 24, 23, 0), 1),    # Sunday 02:00 summer time = 01:00 winter time
    (utc(2026, 10, 25, 10, 0), 12),   # after the switch: +2
])
def test_fallback_uses_the_israel_dst_rule(when, expected_hour):
    assert israel_now_fallback(when).hour == expected_hour


def test_fallback_matches_zoneinfo_all_year():
    zoneinfo = pytest.importorskip("zoneinfo")
    zone = zoneinfo.ZoneInfo("Asia/Jerusalem")
    moment = utc(2025, 1, 1)
    from datetime import timedelta
    while moment.year < 2031:
        real = moment.astimezone(zone).replace(tzinfo=None)
        assert israel_now_fallback(moment) == real, moment
        moment += timedelta(hours=7)


def test_israel_now_falls_back_when_zoneinfo_is_missing(monkeypatch):
    monkeypatch.setattr(hashbrown_text, "_israel_zone", lambda: None)
    assert israel_now(utc(2026, 7, 15, 10, 0)).hour == 13


def test_israel_now_returns_a_naive_datetime():
    assert israel_now().tzinfo is None


def test_israel_time_text_has_day_date_and_time():
    assert hashbrown_text.israel_time_text(utc(2026, 7, 15, 10, 5)) == "Wednesday 2026-07-15 13:05"
