"""
🥔 Hashbrown, the AI member (GPT on Microsoft Foundry).
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

from chatserver import achievements, config, rooms, state, storage, textutil


# ----- 🥔 Hashbrown (GPT on Microsoft Foundry)

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
        textutil.log(f"[HASHBROWN] 🥔 Fill in endpoint and deployment in {config.HASHBROWN_CONFIG}. Hashbrown is off.")
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

def call_hashbrown(messages):
    """Send the conversation to Foundry (Responses API, the same one as client.responses.create)
    and return the answer text. Slow: never call this while holding the lock."""
    if state.hashbrown is None:  # no key: never contact Foundry
        raise RuntimeError("Hashbrown is off (no API key)")
    body = json.dumps({
        "model": state.hashbrown["deployment"],
        "instructions": messages[0]["content"],  # the system prompt
        "input": messages[1:],                  # the chat + question
        "max_output_tokens": 4000,              # thinking models use some of this to think
    }).encode()
    request = urllib.request.Request(state.hashbrown["url"], data=body, method="POST", headers={
        "Content-Type": "application/json",
        "api-key": state.hashbrown["api_key"],
    })
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        hint = HASHBROWN_HINTS.get(e.code, "")
        raise RuntimeError(f"HTTP {e.code} ({hint}): {detail}") from None
    # The answer is in output -> items of type "message" -> parts of type "output_text"
    # (there can also be a "reasoning" item first, which we skip)
    parts = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    parts.append(part.get("text", ""))
    answer = "".join(parts).strip()
    if not answer:
        raise RuntimeError(f"no answer text (status: {data.get('status')})")
    return answer[:1500]

def ask_hashbrown(client, question):
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

    # Give it the recent chat so it knows what everyone is talking about
    recent = "\n".join(f"{m['name']}: {m['text']}" for m in list(state.history[room])[-10:])
    messages = [{"role": "system", "content": config.HASHBROWN_PROMPT},
                {"role": "user", "content": f"Recent chat:\n{recent}\n\n{rooms.nick(key)} asks you: {question}"}]

    # Who pays: the group bank (with the 🥔 upgrade) or the person asking.
    # We remember the group itself, not just its name: it could be disbanded (and a new group
    # with the same name created) before the answer comes back.
    group = state.groups.get(room)
    if group and "hashbrown" in group["upgrades"] and group["bank"] >= config.HASHBROWN_COST:
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
    rooms.notify_room(room, "🥔 Hashbrown is thinking...", kind="event")
    threading.Thread(target=hashbrown_worker, args=(key, room, group, messages, payer), daemon=True).start()

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

def hashbrown_worker(asker, room, group, messages, payer):
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
            if room_still_there:
                rooms.notify_room(room, oops, kind="error")
            else:
                rooms.tell(asker, oops, "error")
            return
        if room_still_there:
            msg = rooms.chat_message("Hashbrown", "🥔", answer)
            state.history[room].append(msg)
            rooms.send_room(room, msg)
            textutil.log(f"[{room}] Hashbrown: {answer}")
        else:  # the group was disbanded while Hashbrown thought: answer just the asker
            rooms.tell(asker, f"🥔 Hashbrown (only you): {answer}", "private")
        if asker in state.accounts:
            achievements.unlock(asker, "potato")
            storage.save_data()
