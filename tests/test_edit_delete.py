"""✏️🗑️ Edit and delete your own messages (for EDIT_MINUTES): {"type": "edit", "id", "text"} and
{"type": "delete", "id"}. The room gets {"type": "edited"} / {"type": "deleted"}; history remembers."""
import sqlite3
import time

import pytest

from chatserver import config, history

pytestmark = pytest.mark.integration


def post(client, text):
    client.line(text)
    return client.expect(lambda m: m.get("type") == "chat" and m.get("text") == text)["id"]


def rejoin_history(client):
    client.line("/create Tmp")
    client.expect_text("Created")
    client.line("/lobby")
    return client.expect(lambda m: m.get("type") == "history" and "Lobby" in m.get("room", ""))["messages"]


def test_editing_your_message_updates_the_room_and_the_history(user):
    adi, ben = user("Adi"), user("Ben")
    message_id = post(adi, "pizza at 7")
    adi.send({"type": "edit", "id": message_id, "text": "pizza at 8"})
    edited = ben.expect(lambda m: m.get("type") == "edited")
    assert (edited["id"], edited["text"]) == (message_id, "pizza at 8")
    old = next(m for m in rejoin_history(adi) if m["id"] == message_id)
    assert old["text"] == "pizza at 8" and old["edited"] is True


def test_deleting_your_message_removes_it(user):
    adi, ben = user("Adi"), user("Ben")
    message_id = post(adi, "oops wrong chat")
    adi.send({"type": "delete", "id": message_id})
    assert ben.expect(lambda m: m.get("type") == "deleted")["id"] == message_id
    assert all(m["id"] != message_id for m in rejoin_history(adi))


def test_you_cant_edit_or_delete_someone_elses_message(user):
    adi, ben = user("Adi"), user("Ben")
    message_id = post(adi, "mine")
    ben.send({"type": "edit", "id": message_id, "text": "hacked"})
    ben.expect_text("only edit or delete your own", kind="error")
    ben.send({"type": "delete", "id": message_id})
    ben.expect_text("only edit or delete your own", kind="error")


def test_renaming_yourself_doesnt_stop_you_editing(user):
    adi = user("Adi")
    message_id = post(adi, "before the rename")
    adi.line("/nick Spud")
    adi.expect_text("You still log in as")
    adi.send({"type": "edit", "id": message_id, "text": "after the rename"})
    assert adi.expect(lambda m: m.get("type") == "edited")["text"] == "after the rename"


def test_too_late_to_edit(user, monkeypatch):
    adi = user("Adi")
    message_id = post(adi, "old news")
    real_time = time.time
    monkeypatch.setattr(history.time, "time", lambda: real_time() + config.EDIT_MINUTES * 60 + 1)
    adi.send({"type": "edit", "id": message_id, "text": "new"})
    adi.expect_text("too old", kind="error")


def test_an_old_history_db_gets_the_new_columns(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as old:
        old.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT, time TEXT, name TEXT, "
                    "badge TEXT, text TEXT, action INTEGER, created REAL)")
        old.execute("INSERT INTO messages (room, time, name, badge, text, action, created) "
                    "VALUES ('lobby', '10:00', 'Adi', '', 'kept', 0, 0)")
    history.close()
    monkeypatch.setattr(config, "HISTORY_DB", str(path))
    assert [m["text"] for m in history.recent("lobby")] == ["kept"]   # nothing lost, and no crash


def test_you_can_only_change_messages_in_the_room_youre_in(user):
    adi = user("Adi")
    message_id = post(adi, "lobby words")
    adi.line("/create Tmp")
    adi.expect_text("Created")
    adi.send({"type": "edit", "id": message_id, "text": "changed from elsewhere"})
    adi.expect_text("room you're in", kind="error")
