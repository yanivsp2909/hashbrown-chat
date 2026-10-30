"""
🥔 Hashbrown, the AI member (GPT on Microsoft Foundry).
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

from chatserver import achievements, config, history, registry, rooms, state, storage, textutil
from chatserver.hashbrown_text import clean_answer, israel_time_text



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
    # Works with https://NAME.openai.azure.com/ or https://NAME.services.ai.azure.com/
    endpoint = str(settings["endpoint"]).strip().rstrip("/")
    if not endpoint.endswith("/openai/v1"):
        endpoint += "/openai/v1"
    settings["url"] = endpoint + "/responses"
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


def explain_http_error(e):
    detail = e.read().decode("utf-8", "replace")[:300]
    hint = HASHBROWN_HINTS.get(e.code, "")
    return RuntimeError(f"HTTP {e.code} ({hint}): {detail}")


def post_to_foundry(body):
    """One request to Foundry. Returns the reply as a dict; raises urllib.error.HTTPError on an error status."""
    request = urllib.request.Request(state.hashbrown["url"], data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json",
        "api-key": state.hashbrown["api_key"],
    })
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def call_hashbrown(messages):
    """Send the conversation to Foundry (Responses API, the same one as client.responses.create)
    and return the cleaned answer text. Slow: never call this while holding the lock."""
    if state.hashbrown is None:  # no key: never contact Foundry
        raise RuntimeError("Hashbrown is off (no API key)")
    body = {
        "model": state.hashbrown["deployment"],
        "instructions": messages[0]["content"],  # the system prompt
        "input": messages[1:],                  # the facts + question
        "max_output_tokens": config.HASHBROWN_MAX_OUTPUT,
    }
    if config.HASHBROWN_REASONING and not state.hashbrown_no_reasoning:
        body["reasoning"] = {"effort": config.HASHBROWN_REASONING}
    try:
        data = post_to_foundry(body)
    except urllib.error.HTTPError as e:
        if e.code != 400 or "reasoning" not in body:
            raise explain_http_error(e) from None
        # Some deployments don't know the reasoning setting: ask again without it, and remember
        if not state.hashbrown_no_reasoning:
            textutil.log("[HASHBROWN] 🥔 This deployment doesn't support reasoning effort. Not sending it from now on.")
        state.hashbrown_no_reasoning = True
        del body["reasoning"]
        try:
            data = post_to_foundry(body)
        except urllib.error.HTTPError as again:
            raise explain_http_error(again) from None
    # The answer is in output -> items of type "message" -> parts of type "output_text"
    # (there can also be a "reasoning" item first, which we skip)
    parts = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    parts.append(part.get("text", ""))
    answer = clean_answer("".join(parts))
    if not answer:
        raise RuntimeError(f"no answer text (status: {data.get('status')})")
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
    threading.Thread(target=hashbrown_worker, args=(key, room, group, messages, payer, private, temp_id),
                     daemon=True).start()


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


def hashbrown_worker(asker, room, group, messages, payer, private, temp_id):
    """Runs in its own thread so the chat keeps working while the AI thinks.
    `group` is the group the question was asked in (None in the lobby)."""
    try:
        answer, error = textutil.clean_text(call_hashbrown(messages), keep_newlines=True), None
    except Exception as e:  # network down, bad key, timeout... the chat must survive all of it
        answer, error = None, e
    with state.lock:
        state.hashbrown_busy -= 1
        room_still_there = state.groups.get(room) is group  # True for the lobby too (None is None)
        if answer is None:
            textutil.log(f"[HASHBROWN] Error: {type(error).__name__}: {error}")
            refund_hashbrown(asker, payer)
            oops = "🥔💥 Hashbrown tripped over something and couldn't answer. The tokens were refunded."
            if room_still_there and not private:
                rooms.notify_room(room, oops, kind="error", replaces=temp_id)
            else:
                rooms.tell(asker, oops, "error", replaces=temp_id)
            return
        if private or not room_still_there:  # /ask, or the group was disbanded while Hashbrown thought
            rooms.tell(asker, f"🥔 Hashbrown (only you): {answer}", "private", replaces=temp_id)
        else:
            msg = rooms.chat_message("Hashbrown", "🥔", answer)
            history.add(room, msg)
            rooms.send_room(room, {**msg, "replaces": temp_id})  # history keeps the plain message
            textutil.log(f"[{room}] Hashbrown: {answer}")
        if asker in state.accounts:
            achievements.unlock(asker, "potato")
            storage.save_data()
