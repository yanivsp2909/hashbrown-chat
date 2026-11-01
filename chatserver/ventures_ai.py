"""
🥔 Hashbrown as the game master of Hashbrown Ventures, done safely:
- it only writes words and picks from choices: the answer is JSON (the Responses API's structured output), and
  `check` reads only the fields it expects, cuts them and throws the rest away. The numbers are always the server's.
- every call counts in VENTURES_AI_PER_DAY and in the server-wide HASHBROWN_DAILY_CAP, at most HASHBROWN_MAX_BUSY
  run at once, and anything that goes wrong (off, cap, busy, error, bad JSON) runs `fallback` instead: the game
  never waits for, or depends on, the AI.
"""
import json
import threading

from chatserver import config, hashbrown_ai, hashbrown_extras, state, textutil


def schema(name, properties):
    """A strict json_schema format: every property required, nothing else allowed."""
    return {"type": "json_schema", "name": name, "strict": True,
            "schema": {"type": "object", "properties": properties, "required": list(properties),
                       "additionalProperties": False}}


def can_ask():
    """True (and counted) if the AI may take one more game call now."""
    day, used = state.ventures_ai_today
    if day != textutil.today():
        day, used = textutil.today(), 0
    if used >= config.VENTURES_AI_PER_DAY or state.hashbrown_busy >= config.HASHBROWN_MAX_BUSY:
        return False
    if not hashbrown_extras.take_server_question():   # (also False when Hashbrown is off)
        return False
    state.ventures_ai_today = (day, used + 1)
    state.hashbrown_busy += 1
    return True


def give_back(day):
    hashbrown_extras.give_back_server_question(day)
    if state.ventures_ai_today[0] == day:
        state.ventures_ai_today = (day, max(0, state.ventures_ai_today[1] - 1))


def ask_json(instructions, text, json_format, check, deliver, fallback):
    """Ask in the background. check(dict) -> the cleaned answer or None; then deliver(answer) or fallback() runs
    while holding the lock (call this while holding it too). Without the AI, fallback() runs right away."""
    if not can_ask():
        fallback()
        return
    day = textutil.today()
    messages = [{"role": "system", "content": instructions}, {"role": "user", "content": text}]

    def work():
        answer, raw = None, None
        try:
            raw = hashbrown_ai.call_hashbrown(messages, clean=False, json_format=json_format,
                                              max_output=config.VENTURES_AI_MAX_OUTPUT,
                                              reasoning=config.VENTURES_AI_REASONING)
        except Exception as e:   # the game must survive anything the network or the AI does
            textutil.log(f"[VENTURES] AI call failed: {hashbrown_ai.describe_error(e)}")
            with state.lock:
                give_back(day)   # (not answered: it shouldn't use up the day's budget)
        try:
            answer = check(parse_json(raw)) if raw else None
        except Exception as e:   # a bad answer is ignored (the fallback runs), but it was paid for
            textutil.log(f"[VENTURES] Couldn't read the AI's answer ({type(e).__name__}).")
        with state.lock:
            state.hashbrown_busy = max(0, state.hashbrown_busy - 1)
            if answer is None:
                fallback()
            else:
                deliver(answer)
    threading.Thread(target=work, daemon=True).start()


def parse_json(raw):
    """The first {...} in the text as a dict, or None."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(raw[start:end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


# ---------------------------------------------------------------- reading the fields safely

def text_field(answer, name, limit=None):
    """A string field, cleaned of control characters and cut, or None."""
    value = answer.get(name) if isinstance(answer, dict) else None
    if not isinstance(value, str):
        return None
    cleaned = textutil.clean_text(value).strip()
    return cleaned[:limit or config.VENTURES_AI_TEXT_MAX] or None


def int_field(answer, name, low, high):
    """A whole number kept inside low..high, or None (true/false and text are not numbers)."""
    value = answer.get(name) if isinstance(answer, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(max(low, min(high, value)))


def choice_field(answer, name, choices):
    value = answer.get(name) if isinstance(answer, dict) else None
    return value if value in choices else None


def is_hebrew(text):
    """True when most letters are Hebrew (the players' language decides the AI's)."""
    hebrew = sum(1 for ch in text if "֐" <= ch <= "׿")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return hebrew > latin


def language(text):
    return "Hebrew" if is_hebrew(text) else "English"
