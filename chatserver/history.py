"""
📜 Chat history, saved in history.db (SQLite) so it survives a restart.

SQL in 30 seconds: a database table is like a spreadsheet. Each message is one ROW.
  INSERT INTO messages (...) VALUES (?, ?, ...)   adds a row (the ? are filled in safely, never paste text into SQL)
  SELECT ... FROM messages WHERE room = ? ORDER BY id DESC LIMIT n   reads the newest n rows of one room
The `id` column counts up by itself (AUTOINCREMENT): that number is the message id the clients see.

If the file can't be opened, the chat keeps working with history kept in memory only.
"""
import sqlite3
import threading
import time
from collections import deque

from chatserver import config, state, textutil

_lock = threading.RLock()
_connection = None       # the open database, or None
_connection_path = None  # which file _connection belongs to
_failed_path = None      # a file we already failed to open (so we log only once)
_memory = {}             # room -> deque of messages, used only when the database is unavailable
_memory_ids = 0          # the id counter for that fallback

_COLUMNS = ("time", "name", "badge", "text", "action")


def _open():
    """The open database connection, or None when it can't be opened."""
    global _connection, _connection_path, _failed_path
    path = config.HISTORY_DB
    if _connection is not None and _connection_path == path:
        return _connection
    if path == _failed_path:
        return None
    close()
    try:
        # One connection shared by all threads: fine, because we use it under _lock.
        connection = sqlite3.connect(path, check_same_thread=False)
        connection.execute("CREATE TABLE IF NOT EXISTS messages ("
                           "id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT, time TEXT, name TEXT, "
                           "badge TEXT, text TEXT, action INTEGER, created REAL)")
        connection.execute("CREATE INDEX IF NOT EXISTS messages_room ON messages (room, id)")
        connection.commit()
    except sqlite3.Error as e:
        _failed_path = path
        textutil.log(f"[SERVER] ⚠️ Can't open {path} ({e}). Chat history is kept in memory only.")
        return None
    _connection, _connection_path = connection, path
    return connection


def close():
    """Close the database file (the data stays in it)."""
    global _connection, _connection_path
    with _lock:
        if _connection is not None:
            _connection.close()
        _connection, _connection_path = None, None


def reset():
    """Forget the connection and the in-memory fallback (the tests use this between tests)."""
    global _failed_path, _memory_ids
    with _lock:
        close()
        _failed_path = None
        _memory.clear()
        _memory_ids = 0


def room_size(room):
    """How many messages a room shows when someone enters (the group's 📜 history upgrade makes it bigger)."""
    group = state.groups.get(room)
    if group is not None and "history" in group["upgrades"]:
        return config.BIG_HISTORY_SIZE
    return config.HISTORY_SIZE


def add(room, msg):
    """Save a chat message (the dict from rooms.chat_message) and put its new "id" in it."""
    global _memory_ids
    with _lock:
        connection = _open()
        if connection is not None:
            try:
                cursor = connection.execute(
                    "INSERT INTO messages (room, time, name, badge, text, action, created) VALUES (?,?,?,?,?,?,?)",
                    (room, msg["time"], msg["name"], msg["badge"], msg["text"], int(bool(msg["action"])),
                     time.time()))
                connection.commit()
                msg["id"] = cursor.lastrowid
                return
            except sqlite3.Error as e:
                textutil.log(f"[SERVER] ⚠️ Couldn't save a message to history.db ({e})")
        _memory_ids += 1
        msg["id"] = _memory_ids
        _memory.setdefault(room, deque(maxlen=config.BIG_HISTORY_SIZE)).append(msg)


def recent(room, count=None):
    """The last `count` messages of a room (default: the room's size), oldest first, each with its "id"."""
    count = room_size(room) if count is None else count
    with _lock:
        connection = _open()
        if connection is None:
            return list(_memory.get(room, ()))[-count:]
        try:
            rows = connection.execute(
                "SELECT id, time, name, badge, text, action FROM messages WHERE room = ? "
                "ORDER BY id DESC LIMIT ?", (room, count)).fetchall()
        except sqlite3.Error as e:
            textutil.log(f"[SERVER] ⚠️ Couldn't read history.db ({e})")
            return list(_memory.get(room, ()))[-count:]
    return [{"type": "chat", "id": row[0], "time": row[1], "name": row[2], "badge": row[3],
             "text": row[4], "action": bool(row[5])} for row in reversed(rows)]


def delete_room(room):
    """Forget a room's messages (a disbanded group must not hand its old chat to a new group with the same name)."""
    with _lock:
        _memory.pop(room, None)
        connection = _open()
        if connection is not None:
            try:
                connection.execute("DELETE FROM messages WHERE room = ?", (room,))
                connection.commit()
            except sqlite3.Error as e:
                textutil.log(f"[SERVER] ⚠️ Couldn't clear a room in history.db ({e})")
