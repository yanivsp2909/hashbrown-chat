"""
🔁 Reconnect and catch up.

Every packet the server keeps for an account gets a "seq" number (an optional field: old clients ignore it).
The last RESUME_KEEP packets (for RESUME_SECONDS) are kept, and for RESUME_SECONDS after a dropped connection
the account's room keeps being collected for it. At login the client gets a "resume_token" (a random secret,
new every time). After a drop it logs in with {"type": "auth", "action": "resume", "username", "token",
"seq": the last one it got} and gets exactly the packets after that seq, without the welcome burst.
Packets that only make sense live (file pieces, typing, pongs, Hashbrown's live pieces, the Groups screen)
get no seq and aren't kept. Leaving with /quit ends it all.
"""
import secrets
import threading
import time
from collections import deque

from chatserver import config, state

LIVE_ONLY = {"auth_result", "netmap", "probe", "stroke", "market", "market_info", "economy", "file", "file_start", "file_chunk", "file_ack", "file_end", "file_cancel", "pong",
             "typing", "typing_stop", "stream", "groups", "group_info"}
_lock = threading.Lock()   # (send() runs in many threads; the seq counter must never give a number twice)


def stamp(key, obj):
    """The packet with its seq number, kept for a possible resume (live-only packets come back unchanged)."""
    if obj.get("type") in LIVE_ONLY:
        return obj
    now = time.time()
    with _lock:
        box = state.replays.setdefault(key, {"seq": 0, "items": deque()})
        box["seq"] += 1
        packet = {**obj, "seq": box["seq"]}
        box["items"].append((now, packet))
        while len(box["items"]) > config.RESUME_KEEP or now - box["items"][0][0] > config.RESUME_SECONDS:
            box["items"].popleft()
    return packet


def missed(key, seq):
    """The kept packets after `seq`, in order; None if some of them aren't kept any more (then: a normal login)."""
    with _lock:
        box = state.replays.get(key)
        if box is None or seq > box["seq"]:
            return None
        items = [packet for _, packet in box["items"] if packet["seq"] > seq]
        last = box["seq"]
    if seq < last and (not items or items[0]["seq"] != seq + 1):
        return None
    return items


def new_token(key, fresh=False):
    """A new secret. The one before it still works once more, in case the answer carrying the new one was lost
    (fresh=True, a password login: no old token keeps working)."""
    old = None if fresh else state.resume_tokens.get(key, {}).get("now")
    token = secrets.token_urlsafe(18)
    state.resume_tokens[key] = {"now": token, "before": old}
    return token


def token_ok(key, token):
    """The right token, and they went away less than RESUME_SECONDS ago (or still look online)."""
    tokens = state.resume_tokens.get(key, {})
    if not isinstance(token, str) or not any(
            good and secrets.compare_digest(token.encode(), good.encode()) for good in (tokens.get("now"), tokens.get("before"))):
        return False
    away = state.away.get(key)
    if key in state.online:
        return not state.online[key].no_resume   # (being kicked right now: no)
    return away is not None and time.time() < away["until"]


def resume_locked(key):
    """Too many wrong tokens for this name lately: no resume for a while (a password login still works)."""
    now = time.time()
    recent = [t for t in state.resume_fails.get(key, []) if now - t < config.LOGIN_FAIL_WINDOW]
    if recent:
        state.resume_fails[key] = recent
    else:
        state.resume_fails.pop(key, None)
    return len(recent) >= config.LOGIN_FAIL_LIMIT


def note_failure(key):
    if key in state.accounts:   # (made-up names aren't remembered: they can't fill the memory)
        state.resume_fails.setdefault(key, []).append(time.time())


def went_away(client):
    """The connection dropped (not /quit): keep collecting their room for a while."""
    state.away[client.key] = {"room": client.room, "features": client.features, "until": time.time() + config.RESUME_SECONDS}


def forget(key):
    """/quit: no coming back with a token."""
    state.away.pop(key, None)
    state.resume_tokens.pop(key, None)
    with _lock:
        state.replays.pop(key, None)


def away_keys():
    """Accounts that dropped less than RESUME_SECONDS ago (the older ones are forgotten here)."""
    now = time.time()
    for key in [k for k, a in state.away.items() if now >= a["until"]]:
        state.away.pop(key, None)
        state.resume_tokens.pop(key, None)
        if key not in state.online:
            with _lock:
                state.replays.pop(key, None)   # they didn't come back: free the kept packets
    return list(state.away)


def record_for_away(room, obj, chat_switcher_member):
    """A room packet that people who just dropped would have got: keep it for their resume."""
    for key in away_keys():
        away = state.away.get(key)
        if away is None or not chat_switcher_member(key, room):   # (kicked from that group meanwhile: nothing)
            continue
        here = away["room"] == room
        if here or ("rooms" in away["features"] and obj.get("type") == "chat" and chat_switcher_member(key, room)):
            stamp(key, {**obj, "room": room} if "rooms" in away["features"] else obj)


def record_to_away(key, obj):
    """A packet for one person (a reminder, a notice) who just dropped."""
    if key in away_keys():
        stamp(key, obj)
