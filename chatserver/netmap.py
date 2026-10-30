"""
🗺️ The live network map (a website page): the server in the middle, every connected player around it, the
packets flying along the lines, and each player's ping. Only counts and types of packets, never their content.

    browser -> server: {"type": "get_netmap"} / {"type": "netmap_closed"}
    server -> browser: {"type": "netmap", "players": [{name, room, ping_ms, in: {type: count}, out: {...}}]}
                       once a second while the page is open (the counts are since the last map)
    server -> client:  {"type": "probe", "id"}     to clients that said "probe" at login, every few seconds
    client -> server:  {"type": "probe_back", "id"} -> its ping is the time in between
Old clients never get probes or maps (their ping is just unknown).
"""
import time

from chatserver import config, rooms, state

_ticks = 0
KNOWN_TYPES = {"auth", "auth_result", "line", "msg", "chat", "history", "rooms", "topic", "file", "file_start",
               "file_chunk", "file_ack", "file_end", "file_cancel", "ping", "pong", "typing", "typing_stop", "react",
               "reactions", "edit", "edited", "delete", "deleted", "stream", "seen", "receipt", "lab", "board",
               "stroke", "draw_round", "probe", "probe_back", "netmap", "groups", "group_info", "profile"}


def handle(client, msg):
    kind = msg.get("type")
    if kind == "netmap_closed":
        client.netmap_open = False
    elif kind == "get_netmap":
        client.netmap_open = True
        client.send(snapshot(reset=False, viewer=client))
    elif kind == "probe_back":
        sent = client.probes.pop(msg.get("id"), None) if isinstance(msg.get("id"), int) else None
        if sent is not None:
            client.ping_ms = round((time.monotonic() - sent) * 1000, 1)


def room_for(viewer, room):
    """A private group's name only for its members (the map mustn't tell who sits in which secret group)."""
    group = state.groups.get(room)
    if group and group["private"] and (viewer is None or viewer.key not in group["members"]):
        return "🔒 a private group"
    return rooms.room_title(room)


def counts(counter):
    """Only packet types the server knows; anything else is "other" (a client can't grow this table)."""
    known = {}
    for kind, n in counter.items():
        name = kind if kind in KNOWN_TYPES else "other"
        known[name] = known.get(name, 0) + n
    return known


def players(viewer):
    return [{"name": rooms.nick(key), "room": room_for(viewer, c.room), "ping_ms": c.ping_ms,
             "in": counts(c.types_in), "out": counts(c.types_out)} for key, c in list(state.online.items())]


def snapshot(reset=True, viewer=None):
    """Everyone connected, with the packets since the last map (reset=False: just look, keep counting)."""
    packet = {"type": "netmap", "players": players(viewer)}
    if reset:
        for c in list(state.online.values()):
            c.types_in.clear()
            c.types_out.clear()
    return packet


def tick(probe=None):
    """Every second: if anyone has the map open, they get a fresh one; every few seconds, the probes go out."""
    global _ticks
    _ticks += 1
    viewers = [c for c in state.online.values() if c.netmap_open]
    if not viewers:
        for c in list(state.online.values()):   # nobody's looking: just start counting again
            c.types_in.clear()
            c.types_out.clear()
        return
    for c in viewers:
        c.send({"type": "netmap", "players": players(c)})
    snapshot(reset=True)
    if probe or (probe is None and _ticks % config.NETMAP_PROBE_EVERY == 0):
        for c in list(state.online.values()):
            if "probe" in c.features:
                c.probe_count += 1
                c.probes = {c.probe_count: time.monotonic()}   # only the newest counts
                c.send({"type": "probe", "id": c.probe_count})
