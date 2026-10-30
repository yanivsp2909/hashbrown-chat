"""🗺️ The live network map: {"type": "get_netmap"} -> once a second {"type": "netmap", "players": [...]} with each
connected player's room, packets per type in and out since the last map (never their content) and ping.
The ping: the server sends {"type": "probe", "id"} to clients that said "probe" at login and times their
{"type": "probe_back", "id"}. Old clients never get probes (their ping is just unknown)."""
import pytest

from chatserver import netmap, state

pytestmark = pytest.mark.integration


def tick():
    with state.lock:
        netmap.tick(probe=True)


def latest_map(client):
    return client.expect(lambda m: m.get("type") == "netmap")


def test_the_map_shows_players_and_packet_counts_by_type(user):
    adi, ben = user("Adi"), user("Ben")
    adi.send({"type": "get_netmap"})
    first = latest_map(adi)
    assert {p["name"] for p in first["players"]} == {"Adi", "Ben"}
    ben.line("hello")
    ben.line("hello again")
    adi.expect(lambda m: m.get("text") == "hello again")
    ben.expect(lambda m: m.get("text") == "hello again")   # (Ben's own copy counted as sent to him)
    tick()
    seen = next(p for p in latest_map(adi)["players"] if p["name"] == "Ben")
    assert seen["in"].get("line") == 2 and seen["out"].get("chat") == 2 and seen["room"] == "🏠 Lobby"
    assert "hello" not in str(latest_map.__doc__ or "") and all("text" not in p for p in first["players"])


def test_probes_measure_the_ping_of_clients_that_answer(user):
    adi = user("Adi", features=["probe"])
    old = user("Old")
    adi.send({"type": "get_netmap"})
    latest_map(adi)
    tick()
    probe = adi.expect(lambda m: m.get("type") == "probe")
    adi.send({"type": "probe_back", "id": probe["id"]})
    adi.line("/users")
    adi.expect_text("Online now")
    tick()
    players = {p["name"]: p for p in latest_map(adi)["players"]}
    assert isinstance(players["Adi"]["ping_ms"], (int, float)) and players["Adi"]["ping_ms"] >= 0
    assert players["Old"]["ping_ms"] is None
    old.line("/users")
    old.expect_text("Online now")
    assert not [m for m in old.messages if m.get("type") == "probe"]


def test_a_closed_map_gets_nothing_and_old_clients_never_do(user):
    adi, old = user("Adi"), user("Old")
    adi.send({"type": "get_netmap"})
    latest_map(adi)
    adi.send({"type": "netmap_closed"})
    adi.line("/users")
    adi.expect_text("Online now")
    count = len([m for m in adi.messages if m.get("type") == "netmap"])
    tick()
    adi.line("/users")
    adi.expect_text("Online now")
    assert len([m for m in adi.messages if m.get("type") == "netmap"]) == count
    assert not [m for m in old.messages if m.get("type") in ("netmap", "probe")]


def test_a_wrong_probe_answer_is_ignored(user):
    adi = user("Adi", features=["probe"])
    adi.send({"type": "probe_back", "id": "nonsense"})
    adi.send({"type": "probe_back", "id": 99999})
    adi.send({"type": "get_netmap"})
    me = next(p for p in latest_map(adi)["players"] if p["name"] == "Adi")
    assert me["ping_ms"] is None


def test_private_groups_are_hidden_from_outsiders_and_junk_types_are_other(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/create Secret private")
    adi.expect_text("Created")
    ben.send({"type": "made_up_type_1"})
    ben.send({"type": "made_up_type_2"})
    ben.send({"type": "get_netmap"})
    rows = {p["name"]: p for p in latest_map(ben)["players"]}
    assert rows["Adi"]["room"] == "🔒 a private group"
    assert set(rows["Ben"]["in"]) <= set(netmap.KNOWN_TYPES) | {"other"}
    adi.send({"type": "get_netmap"})
    assert {p["name"]: p for p in latest_map(adi)["players"]}["Adi"]["room"] == "🔒Secret"
