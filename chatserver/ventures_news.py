"""
📰 Ventures News: a headline for everything that happens (founding, rounds, launches, breaches, deaths, events...).
The last NEWS_KEPT are saved with the game (the website's feed); every one also goes to history.db (venture_news).
Big ones are also said in the lobby, and Hashbrown may add one funny line to them (VENTURES_NEWS_AI_PER_DAY, the
template headline is always there first, so the feed works without the AI).
"""
import time

from chatserver import config, history, rooms, state, textutil, ventures_ai, ventures_store

LINE_FORMAT = ventures_ai.schema("news_line", {"line": {"type": "string"}})


def feed(company=None, limit=20):
    """Newest first; only one company's when `company` (an id) is given."""
    news = ventures_store.ensure()["news"]
    picked = [n for n in news if company is None or n.get("company") == company]
    return list(reversed(picked))[:limit]


def add(kind, headline, company=None, text="", big=False):
    """A new headline. company: the company's record (or None for the whole market)."""
    ventures = ventures_store.ensure()
    entry = {"id": ventures.get("news_id", 0) + 1, "time": int(time.time()), "tick": ventures["tick"],
             "season": ventures["season"], "kind": kind, "headline": headline[:160], "text": text[:300],
             "company": company["id"] if company else "", "name": company["name"] if company else ""}
    ventures_store.set_field("news_id", entry["id"])
    ventures_store.set_field("news", (ventures["news"] + [entry])[-config.NEWS_KEPT:])
    history.run(lambda c: (c.execute("INSERT INTO venture_news (time, season, tick, kind, company, headline, text) "
                                     "VALUES (?,?,?,?,?,?,?)", (entry["time"], entry["season"], entry["tick"], kind,
                                                                entry["company"], entry["headline"], entry["text"])),
                           c.commit()))
    if big:
        rooms.announce(f"📰 {headline}")
        add_funny_line(entry)
    return entry


def add_funny_line(entry):
    """🥔 Hashbrown writes one funny line for a big headline (counted in the game's AI budget; nothing without it)."""
    if state.hashbrown is None:   # (Hashbrown is off: the template headline is the news)
        return
    used_day, used = state.ventures_ai_today
    if textutil.today() == used_day and used >= config.VENTURES_AI_PER_DAY:
        return
    news_today = ventures_store.ensure().get("news_ai", ["", 0])
    if news_today[0] == textutil.today() and news_today[1] >= config.VENTURES_NEWS_AI_PER_DAY:
        return
    ventures_store.set_field("news_ai", [textutil.today(), (news_today[1] if news_today[0] == textutil.today() else 0) + 1])
    instructions = ("You write the funny one-line comment under a headline of \"Ventures News\", the tabloid of a startup "
                    "game in a school chat. One sentence, at most 140 characters, playful, never mean about a real "
                    "person, no new numbers. Reply only with JSON in the required format. Answer in English.")
    ventures_ai.ask_json(instructions, f"Headline: {entry['headline']}", LINE_FORMAT,
                         lambda answer: ventures_ai.text_field(answer, "line", 140),
                         lambda line: set_text(entry["id"], line), lambda: None)


def set_text(news_id, line):
    news = ventures_store.ensure()["news"]
    ventures_store.set_field("news", [{**n, "text": line} if n["id"] == news_id else n for n in news])


def clean_saved(value):
    if not isinstance(value, list):
        return []
    return [n for n in value if isinstance(n, dict) and isinstance(n.get("headline"), str)
            and isinstance(n.get("id"), int)][-config.NEWS_KEPT:]
