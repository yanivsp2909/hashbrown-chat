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


def handle(client, msg):
    kind = msg.get("type")
    if kind == "netmap_closed":
        client.netmap_open = False
    elif kind == "get_netmap":
        client.netmap_open = True
        client.send(snapshot(reset=False))
    elif kind == "probe_back":
        sent = client.probes.pop(msg.get("id"), None) if isinstance(msg.get("id"), int) else None
        if sent is not None:
            client.ping_ms = round((time.monotonic() - sent) * 1000, 1)


def snapshot(reset=True):
    """Everyone connected, with the packets since the last map (reset=False: just look, keep counting)."""
    players = []
    for key, c in list(state.online.items()):
        players.append({"name": rooms.nick(key), "room": rooms.room_title(c.room), "ping_ms": c.ping_ms,
                        "in": dict(c.types_in), "out": dict(c.types_out)})
        if reset:
            c.types_in.clear()
            c.types_out.clear()
    return {"type": "netmap", "players": players}


def tick(probe=None):
    """Every second: if anyone has the map open, they get a fresh one; every few seconds, the probes go out."""
    global _ticks
    _ticks += 1
    viewers = [c for c in state.online.values() if c.netmap_open]
    if not viewers:
        return
    packet = snapshot()
    for c in viewers:
        c.send(packet)
    if probe or (probe is None and _ticks % config.NETMAP_PROBE_EVERY == 0):
        for c in list(state.online.values()):
            if "probe" in c.features:
                c.probe_count += 1
                c.probes = {c.probe_count: time.monotonic()}   # only the newest counts
                c.send({"type": "probe", "id": c.probe_count})
