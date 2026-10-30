"""
🥔 Hashbrown, the AI member (GPT on Microsoft Foundry, through the official `openai` package).
"""
import json
import os
import threading
import time

from chatserver import achievements, config, history, registry, rooms, state, storage, textutil
from chatserver.hashbrown_text import clean_answer, israel_time_text

REQUEST_TIMEOUT = 90         # seconds the AI may stay silent
STREAM_SEND_EVERY = 0.15     # seconds: send a live piece at most this often...
STREAM_SEND_CHARS = 40       # ...or as soon as this many new characters are waiting
RAW_LENGTH_FACTOR = 4        # stop reading an answer that grows past this many times the allowed length
CODE_LINE_CHARS = 100        # room per allowed code line, added to that limit


def import_openai():
    """The openai package, or None if it isn't installed (then Hashbrown stays off and the chat still works).
    Imported here, not at the top, so the server starts without it."""
    try:
        import openai
    except ImportError:
        return None
    return openai


def is_placeholder(value):
    """True if a setting is missing, empty, or still the template text (like PASTE-YOUR-KEY-HERE)."""
    value = str(value or "").strip()
    return not value or "PASTE" in value or "YOUR-" in value or "YOUR_" in value


def hashbrown_key(settings):
    """The API key: the HASHBROWN_API_KEY environment variable wins, otherwise api_key from
    hashbrown_config.json. Returns "" if neither has a real key.
    Never print, log or save what this returns, not even part of it."""
    key = os.environ.get("HASHBROWN_API_KEY", "").strip() or str(settings.get("api_key") or "").strip()
    return "" if is_placeholder(key) else key


def load_hashbrown():
    """Read hashbrown_config.json. Returns the settings, or None if Hashbrown is off."""
    if not os.path.exists(config.HASHBROWN_CONFIG):
        template = {"endpoint": "https://YOUR-RESOURCE.services.ai.azure.com/openai/v1",
                    "deployment": "gpt-6.1-terra",
                    "api_key": "PASTE-YOUR-KEY-HERE"}
        with open(config.HASHBROWN_CONFIG, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
        textutil.log(f"[HASHBROWN] 🥔 Created {config.HASHBROWN_CONFIG}.")
    try:
        with open(config.HASHBROWN_CONFIG, encoding="utf-8") as f:
            settings = json.load(f)
    except (OSError, ValueError) as e:
        # Only the error's type: its message could quote bytes from the file
        textutil.log(f"[HASHBROWN] Can't read {config.HASHBROWN_CONFIG} ({type(e).__name__}). Hashbrown is off.")
        return None
    if not isinstance(settings, dict):
        textutil.log(f"[HASHBROWN] {config.HASHBROWN_CONFIG} should be a JSON object. Hashbrown is off.")
        return None
    settings["api_key"] = hashbrown_key(settings)
    if not settings["api_key"]:
        textutil.log("[HASHBROWN] 🥔 No API key, so Hashbrown is off. Set the HASHBROWN_API_KEY environment variable "
                     "and restart the server.")
        return None
    if is_placeholder(settings.get("endpoint")) or is_placeholder(settings.get("deployment")):
        textutil.log(f"[HASHBROWN] 🥔 Fill in endpoint and deployment in {config.HASHBROWN_CONFIG}. "
                     "Hashbrown is off.")
        return None
    if import_openai() is None:
        textutil.log("[HASHBROWN] 🥔 Hashbrown needs the openai package: pip install -r requirements.txt")
        return None
    # Works with https://NAME.openai.azure.com/ or https://NAME.services.ai.azure.com/
    endpoint = str(settings["endpoint"]).strip().rstrip("/")
    if not endpoint.endswith("/openai/v1"):
        endpoint += "/openai/v1"
    settings["base_url"] = endpoint  # the openai package adds /responses itself
    textutil.log(f"[HASHBROWN] 🥔 Awake! Using deployment '{settings['deployment']}'")
    return settings


HASHBROWN_HINTS = {401: "the API key (HASHBROWN_API_KEY) is wrong",
                   403: "this key isn't allowed to use the resource",
                   404: "the endpoint or deployment name in hashbrown_config.json is wrong",
                   429: "too many requests or out of quota, wait a bit"}


def command_list():
    """Every /command with what it does, grouped like /help. Read from the registry each time,
    so a new command is known to Hashbrown without touching this file."""
    by_category = {}
    for function, usage, description, category in registry.COMMANDS.values():
        by_category.setdefault(category, []).append(f"  {usage}: {description}")
    lines = []
    for category, items in by_category.items():
        lines.append(f"{category}")
        lines += items
    return "\n".join(lines)


def build_messages(key, room, question):
    """[system, user] for one question. The system part is the personality plus the command list;
    the user part has the facts of this moment (who asks, where, when, who is online, the recent chat)."""
    recent = "\n".join(f"{m['name']}: {m['text']}" for m in history.recent(room, config.HASHBROWN_HISTORY))
    online = ", ".join(rooms.nick(k) for k in state.online)
    facts = (f"Asking: {rooms.nick(key)}\n"
             f"Room: {rooms.room_title(room)}\n"
             f"Time in Israel: {israel_time_text()}\n"
             f"Online now: {online}\n\n"
             f"Recent chat:\n{recent}\n\n"
             f"{rooms.nick(key)} asks you: {question}")
    system = f"{config.HASHBROWN_PROMPT}\n\nThe app's commands:\n{command_list()}"
    return [{"role": "system", "content": system}, {"role": "user", "content": facts}]


def describe_error(e):
    """A safe one-line description of an error for the log: the class name, the HTTP status and a hint.
    Never str(e): the text of an API error can quote the request, and the key must never reach the log."""
    status = getattr(e, "status_code", None)
    if status is None:
        return type(e).__name__
    return f"{type(e).__name__} (HTTP {status}{', ' + HASHBROWN_HINTS[status] if status in HASHBROWN_HINTS else ''})"


def max_raw_length():
    """The longest raw answer worth reading. clean_answer cuts to far less; past this we stop the stream."""
    return RAW_LENGTH_FACTOR * config.HASHBROWN_MAX_CHARS + config.HASHBROWN_MAX_CODE_LINES * CODE_LINE_CHARS


def read_stream(client, request, on_text):
    """Send one request and read the answer piece by piece. on_text(piece) gets each new piece of text.
    Returns the whole raw text. Raises if the stream breaks before the end."""
    stream = client.responses.create(**request, stream=True)
    pieces, length, finished = [], 0, False
    try:
        for event in stream:
            if event.type == "response.output_text.delta":
                pieces.append(event.delta)
                length += len(event.delta)
                on_text(event.delta)
                if length > max_raw_length():  # a runaway answer: stop paying attention to it
                    finished = True
                    break
            elif event.type == "response.completed":
                finished = True
                break
            elif event.type in ("response.failed", "response.incomplete", "error"):
                raise RuntimeError(f"the AI ended the answer early ({event.type})")
    finally:
        stream.close()
    if not finished:
        raise RuntimeError("the connection ended before the answer was complete")
    return "".join(pieces)


def call_hashbrown(messages, on_text=None):
    """Send the conversation to Foundry (Responses API, like client.responses.create(..., stream=True))
    and return the cleaned answer text. on_text(piece) is called for every piece as it arrives.
    Slow: never call this while holding the lock."""
    if state.hashbrown is None:  # no key: never contact Foundry
        raise RuntimeError("Hashbrown is off (no API key)")
    openai = import_openai()
    if openai is None:
        raise RuntimeError("the openai package is missing")
    on_text = on_text or (lambda piece: None)
    request = {
        "model": state.hashbrown["deployment"],
        "instructions": messages[0]["content"],  # the system prompt
        "input": messages[1:],                  # the facts + question
        "max_output_tokens": config.HASHBROWN_MAX_OUTPUT,
    }
    if config.HASHBROWN_REASONING and not state.hashbrown_no_reasoning:
        request["reasoning"] = {"effort": config.HASHBROWN_REASONING}
    # max_retries=0: a failed question is refunded, and we don't want hidden waits
    client = openai.OpenAI(base_url=state.hashbrown["base_url"], api_key=state.hashbrown["api_key"],
                           timeout=REQUEST_TIMEOUT, max_retries=0)
    try:
        try:
            raw = read_stream(client, request, on_text)
        except openai.BadRequestError:
            if "reasoning" not in request:
                raise
            # Some deployments don't know the reasoning setting: ask again without it. Only if that
            # works do we remember it (a 400 can also be a content filter, which has nothing to do with it).
            del request["reasoning"]
            raw = read_stream(client, request, on_text)
            if not state.hashbrown_no_reasoning:
                textutil.log("[HASHBROWN] 🥔 This deployment doesn't support reasoning effort. "
                             "Not sending it from now on.")
            state.hashbrown_no_reasoning = True
    finally:
        client.close()
    answer = clean_answer(raw)
    if not answer:
        raise RuntimeError("no answer text")
    return answer


def ask_hashbrown(client, question, private=False):
    """Check the rules, take the payment and start the worker thread.
    private=True is /ask: only the asker sees the thinking notice and the answer, and they always pay."""
    if state.hashbrown is None:
        client.say("🥔💤 Hashbrown is asleep (the server owner hasn't set it up yet).", "error")
        return
    if not question:
        client.say("🥔 Ask something! Like: @hashbrown tell me a joke", "error")
        return
    key, room = client.key, client.room
    wait = state.hashbrown_last.get(key, 0) + config.HASHBROWN_COOLDOWN - time.time()
    if wait > 0:
        client.say(f"🥔 Hashbrown needs a breather. Ask again in {int(wait) + 1}s.", "error")
        return
    day, asked = state.hashbrown_today.get(key, ("", 0))
    if day != textutil.today():
        day, asked = textutil.today(), 0
    if asked >= config.HASHBROWN_DAILY_LIMIT:
        client.say(f"🥔 You've asked {config.HASHBROWN_DAILY_LIMIT} questions today. Come back tomorrow!", "error")
        return
    all_day, all_asked = state.hashbrown_all_today
    if all_day != textutil.today():
        all_day, all_asked = textutil.today(), 0
    if all_asked >= config.HASHBROWN_DAILY_CAP:
        client.say(f"🥔😴 Hashbrown already answered {config.HASHBROWN_DAILY_CAP} questions today and is taking "
                   f"a nap. Ask again tomorrow!", "error")
        return
    if state.hashbrown_busy >= config.HASHBROWN_MAX_BUSY:
        client.say("🥔 Hashbrown is busy answering others. Try again in a few seconds.", "error")
        return

    messages = build_messages(key, room, question)

    # Who pays: the group bank (with the 🥔 upgrade) or the person asking.
    # We remember the group itself, not just its name: it could be disbanded (and a new group
    # with the same name created) before the answer comes back.
    group = state.groups.get(room)
    if group and not private and "hashbrown" in group["upgrades"] and group["bank"] >= config.HASHBROWN_COST:
        group["bank"] -= config.HASHBROWN_COST
        payer = ("group", group)
    elif state.accounts[key]["tokens"] >= config.HASHBROWN_COST:
        state.accounts[key]["tokens"] -= config.HASHBROWN_COST
        payer = ("user", key)
    else:
        client.say(f"💸 Asking Hashbrown costs {config.HASHBROWN_COST} 🪙.", "error")
        return

    state.hashbrown_last[key] = time.time()
    state.hashbrown_today[key] = (day, asked + 1)
    state.hashbrown_all_today = (all_day, all_asked + 1)
    state.hashbrown_busy += 1
    # The notice gets a temp_id; the answer (or the error) says "replaces": that id, so the
    # website can swap the notice for the answer. Old clients ignore both fields.
    state.hashbrown_questions += 1
    temp_id = f"hb-{state.hashbrown_questions}"
    if private:
        client.say("🥔 Hashbrown is thinking...", "event", temp_id=temp_id)
    else:
        rooms.notify_room(room, "🥔 Hashbrown is thinking...", kind="event", temp_id=temp_id)
    try:
        threading.Thread(target=hashbrown_worker, args=(key, room, group, messages, payer, private, temp_id),
                         daemon=True).start()
    except RuntimeError:  # the computer can't start another thread right now: undo everything
        state.hashbrown_busy -= 1
        refund_hashbrown(key, payer)
        client.say("🥔💥 Hashbrown is too busy right now. The tokens were refunded.", "error", replaces=temp_id)


def refund_hashbrown(asker, payer):
    """The question failed: give the tokens back and don't count it as one of today's questions."""
    kind, who = payer
    if kind == "user" and who in state.accounts:
        state.accounts[who]["tokens"] += config.HASHBROWN_COST
    elif kind == "group" and state.groups.get(who["name"].lower()) is who:
        who["bank"] += config.HASHBROWN_COST
    elif kind == "group" and who["owner"] in state.accounts:  # the group is gone: its bank went to the owner
        state.accounts[who["owner"]]["tokens"] += config.HASHBROWN_COST
    day, asked = state.hashbrown_today.get(asker, ("", 0))
    if day == textutil.today() and asked > 0:
        state.hashbrown_today[asker] = (day, asked - 1)
    all_day, all_asked = state.hashbrown_all_today
    if all_day == textutil.today() and all_asked > 0:
        state.hashbrown_all_today = (all_day, all_asked - 1)


class LiveStream:
    """Sends Hashbrown's answer, piece by piece, to the people who asked for "stream" at login.
    Pieces are batched (a packet at most every STREAM_SEND_EVERY seconds, or when STREAM_SEND_CHARS new
    characters are waiting) so a fast AI can't flood anybody's outbox. The thinking notice's temp_id is
    the stream_id: the first packet also says "replaces", so the website swaps the notice for the live bubble."""

    def __init__(self, asker, room, group, private, temp_id):
        self.asker, self.room, self.group, self.private, self.temp_id = asker, room, group, private, temp_id
        self.time = rooms.chat_message("", "", "")["time"]
        self.waiting = ""     # text received but not sent yet
        self.last_sent = 0    # time.monotonic() of the last packet
        self.started = False  # has the first packet gone out?

    def audience(self):
        """The clients that get the live pieces. Call while holding the lock."""
        if self.private:
            targets = [state.online.get(self.asker)]
        elif state.groups.get(self.room) is not self.group:   # the group was disbanded: only the asker is left
            targets = [state.online.get(self.asker)]
        else:
            targets = [c for c in list(state.online.values()) if c.room == self.room]
        return [c for c in targets if c is not None and "stream" in c.features]

    def send(self, packet):
        """Call while holding the lock."""
        for client in self.audience():
            client.send({"type": "stream", "stream_id": self.temp_id, **packet})

    def flush(self):
        """Call while holding the lock."""
        if not self.waiting:
            return
        packet = {"name": "Hashbrown", "badge": "🥔", "time": self.time, "append": self.waiting}
        if not self.started:
            packet["replaces"] = self.temp_id
        self.send(packet)
        self.started, self.waiting, self.last_sent = True, "", time.monotonic()

    def feed(self, piece):
        """A new piece of text arrived (worker thread, lock NOT held)."""
        self.waiting += piece
        if len(self.waiting) >= STREAM_SEND_CHARS or time.monotonic() - self.last_sent >= STREAM_SEND_EVERY:
            with state.lock:
                self.flush()

    def fail(self):
        """The answer broke: tell the streaming clients to drop the live bubble. Call while holding the lock."""
        if self.started:
            self.send({"done": True, "failed": True})


def hashbrown_worker(asker, room, group, messages, payer, private, temp_id):
    """Runs in its own thread so the chat keeps working while the AI thinks.
    `group` is the group the question was asked in (None in the lobby)."""
    live = LiveStream(asker, room, group, private, temp_id)
    try:
        answer, error = textutil.clean_text(call_hashbrown(messages, live.feed), keep_newlines=True), None
    except Exception as e:  # network down, bad key, timeout... the chat must survive all of it
        answer, error = None, e
    with state.lock:
        state.hashbrown_busy -= 1
        room_still_there = state.groups.get(room) is group  # True for the lobby too (None is None)
        if answer is None:
            textutil.log(f"[HASHBROWN] Error: {describe_error(error)}")
            live.fail()
            refund_hashbrown(asker, payer)
            oops = "🥔💥 Hashbrown tripped over something and couldn't answer. The tokens were refunded."
            if room_still_there and not private:
                rooms.notify_room(room, oops, kind="error", replaces=temp_id)
            else:
                rooms.tell(asker, oops, "error", replaces=temp_id)
            return
        live.flush()
        # "stream_id" + "done" tell streaming clients to swap their live bubble for this final text
        done = {"replaces": temp_id, "stream_id": temp_id, "done": True}
        if private or not room_still_there:  # /ask, or the group was disbanded while Hashbrown thought
            rooms.tell(asker, f"🥔 Hashbrown (only you): {answer}", "private", **done)
        else:
            msg = rooms.chat_message("Hashbrown", "🥔", answer)
            history.add(room, msg)
            rooms.send_room(room, {**msg, **done})  # history keeps the plain message
            textutil.log(f"[{room}] Hashbrown: {answer}")
        if asker in state.accounts:
            achievements.unlock(asker, "potato")
            storage.save_data()
