"""📜 Chat history in SQLite: ids, the last N messages per room, surviving a restart."""
import json
import threading

from chatserver import config, connections, history, state, session
from helpers import FakeClient, auth


def last_history(client):
    return client.expect(lambda m: m.get("type") == "history")["messages"]


def rejoin_lobby(client):
    """What the lobby shows when someone enters it (the client goes to a group and back first)."""
    name = f"Room{len(client.messages)}"
    state.accounts[client.name.lower()]["tokens"] += 100
    client.line(f"/create {name}")
    last_history(client)
    client.line("/lobby")
    return last_history(client)


def test_chat_lines_get_increasing_ids(user):
    adi = user("Adi")
    adi.line("one")
    first = adi.expect(lambda m: m.get("type") == "chat" and m["text"] == "one")
    adi.line("two")
    second = adi.expect(lambda m: m.get("type") == "chat" and m["text"] == "two")
    assert isinstance(first["id"], int)
    assert second["id"] > first["id"]


def test_history_on_join_has_ids_oldest_first(user):
    adi = user("Adi")
    for word in ("a", "b", "c"):
        adi.line(word)
    adi.sync()
    ben = user("Ben")
    messages = rejoin_lobby(ben)
    assert [m["text"] for m in messages] == ["a", "b", "c"]
    assert all(isinstance(m["id"], int) for m in messages)
    assert [m["id"] for m in messages] == sorted(m["id"] for m in messages)


def test_history_keeps_only_the_last_n(user):
    adi = user("Adi")
    for i in range(config.HISTORY_SIZE + 5):
        adi.line(f"m{i}")
    adi.sync()
    messages = rejoin_lobby(adi)
    assert len(messages) == config.HISTORY_SIZE
    assert messages[-1]["text"] == f"m{config.HISTORY_SIZE + 4}"
    assert messages[0]["text"] == "m5"


def test_history_upgrade_gives_the_bigger_n(user):
    adi = user("Adi")
    adi.line("/create Potatoes")
    adi.expect(lambda m: m.get("type") == "history")
    state.groups["potatoes"]["upgrades"].append("history")
    for i in range(config.BIG_HISTORY_SIZE + 3):
        adi.line(f"m{i}")
    adi.sync()
    adi.line("/lobby")
    last_history(adi)
    adi.line("/join potatoes")
    messages = last_history(adi)
    assert len(messages) == config.BIG_HISTORY_SIZE


def test_history_is_per_room(user):
    adi = user("Adi")
    adi.line("lobby words")
    adi.line("/create Potatoes")
    adi.expect(lambda m: m.get("type") == "history")
    adi.line("group words")
    adi.sync()
    adi.line("/lobby")
    assert [m["text"] for m in last_history(adi)] == ["lobby words"]
    adi.line("/join potatoes")
    assert [m["text"] for m in last_history(adi)] == ["group words"]


def test_disbanded_group_history_does_not_come_back(user):
    adi = user("Adi")
    adi.line("/create Potatoes")
    adi.expect(lambda m: m.get("type") == "history")
    adi.line("secret")
    adi.sync()
    adi.line("/disband")
    adi.expect(lambda m: m.get("type") == "history")
    state.accounts["adi"]["tokens"] = 1000
    adi.line("/create Potatoes")
    assert last_history(adi) == []


def test_hashbrown_answer_is_stored_with_an_id(user, fake_hashbrown):
    adi = user("Adi")
    adi.line("@hashbrown hi")
    answer = adi.expect(lambda m: m.get("type") == "chat" and m["name"] == "Hashbrown")
    assert isinstance(answer["id"], int)
    adi.sync()
    assert any(m["name"] == "Hashbrown" and m["id"] == answer["id"] for m in rejoin_lobby(adi))


def test_history_survives_a_server_restart(user, chat_server):
    adi = user("Adi")
    adi.line("remember me")
    adi.sync()
    history.reset()  # like stopping the server: the connection closes, the file stays
    state.reset_state()
    listener = connections.start_server("127.0.0.1", 0, run_loops=False, run_console=False)
    thread = threading.Thread(target=connections.serve_forever, args=(listener,), daemon=True)
    thread.start()
    try:
        client = FakeClient(listener.getsockname()[1])
        assert auth(client, "login", "Adi", "pass1234")["ok"]
        messages = last_history(client)
        assert [m["text"] for m in messages] == ["remember me"]
        client.line("after")
        new = client.expect(lambda m: m.get("type") == "chat" and m["text"] == "after")
        assert new["id"] > messages[0]["id"]  # ids keep counting, they never repeat
        client.close()
    finally:
        with state.lock:
            clients = list(state.online.values())
        for c in clients:
            session.hang_up(c)
        listener.close()
        thread.join(5)


def test_chat_keeps_working_if_the_database_cannot_open(user, monkeypatch, tmp_path):
    history.reset()
    monkeypatch.setattr(config, "HISTORY_DB", str(tmp_path / "no_such_folder" / "x" / "history.db"))
    adi = user("Adi")
    adi.line("still here")
    chat = adi.expect(lambda m: m.get("type") == "chat" and m["text"] == "still here")
    assert isinstance(chat["id"], int)
    assert [m["text"] for m in rejoin_lobby(adi)] == ["still here"]


def test_unicode_and_sql_characters_are_stored_as_text(user):
    adi = user("Adi")
    adi.line("'); DROP TABLE messages;-- 🥔 שלום")
    adi.sync()
    assert [m["text"] for m in rejoin_lobby(adi)] == ["'); DROP TABLE messages;-- 🥔 שלום"]
    assert json.dumps(history.recent("lobby", 5))
