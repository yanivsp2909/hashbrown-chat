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
        # ✏️ added later: who wrote it (their login, which never changes) and whether it was edited.
        # An older history.db gets the new columns here, keeping every message.
        columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
        if "login" not in columns:
            connection.execute("ALTER TABLE messages ADD COLUMN login TEXT")
        if "edited" not in columns:
            connection.execute("ALTER TABLE messages ADD COLUMN edited INTEGER DEFAULT 0")
        # 😂 one row per (message, person, emoji): reacting again deletes the row
        connection.execute("CREATE TABLE IF NOT EXISTS reactions (message_id INTEGER, login TEXT, emoji TEXT, "
                           "PRIMARY KEY (message_id, login, emoji))")
        # 🏦 every change of a group bank (bank_log.py): who, how much, why, and the balance after it
        connection.execute("CREATE TABLE IF NOT EXISTS bank_log (id INTEGER PRIMARY KEY AUTOINCREMENT, grp TEXT, "
                           "time REAL, kind TEXT, who TEXT, amount INTEGER, note TEXT, balance INTEGER)")
        connection.execute("CREATE INDEX IF NOT EXISTS bank_log_grp ON bank_log (grp, id)")
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


def run(job, default=None):
    """job(connection) with the database locked; `default` if history.db can't be opened or the job fails."""
    with _lock:
        connection = _open()
        if connection is None:
            return default
        try:
            return job(connection)
        except sqlite3.Error as e:
            connection.rollback()
            textutil.log(f"[SERVER] ⚠️ history.db: {e}")
            return default


def room_size(room):
    """How many messages a room shows when someone enters (the group's 📜 history upgrade makes it bigger)."""
    group = state.groups.get(room)
    if group is not None and "history" in group["upgrades"]:
        return config.BIG_HISTORY_SIZE
    return config.HISTORY_SIZE


def add(room, msg, login=None):
    """Save a chat message (the dict from rooms.chat_message) and put its new "id" in it.
    login = who wrote it (None for Hashbrown), so only they can edit or delete it."""
    global _memory_ids
    with _lock:
        connection = _open()
        if connection is not None:
            try:
                cursor = connection.execute(
                    "INSERT INTO messages (room, time, name, badge, text, action, created, login) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (room, msg["time"], msg["name"], msg["badge"], msg["text"], int(bool(msg["action"])),
                     time.time(), login))
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
                "SELECT id, time, name, badge, text, action, edited FROM messages WHERE room = ? "
                "ORDER BY id DESC LIMIT ?", (room, count)).fetchall()
        except sqlite3.Error as e:
            textutil.log(f"[SERVER] ⚠️ Couldn't read history.db ({e})")
            return list(_memory.get(room, ()))[-count:]
        counts = reaction_counts([row[0] for row in rows])
    messages = [{"type": "chat", "id": row[0], "time": row[1], "name": row[2], "badge": row[3],
                 "text": row[4], "action": bool(row[5]), **({"edited": True} if row[6] else {})}
                for row in reversed(rows)]
    return [{**m, "reactions": counts[m["id"]]} if m["id"] in counts else m for m in messages]


def delete_room(room):
    """Forget a room's messages (a disbanded group must not hand its old chat to a new group with the same name)."""
    with _lock:
        _memory.pop(room, None)
        connection = _open()
        if connection is not None:
            try:
                connection.execute("DELETE FROM reactions WHERE message_id IN "
                                   "(SELECT id FROM messages WHERE room = ?)", (room,))
                connection.execute("DELETE FROM messages WHERE room = ?", (room,))
                connection.commit()
            except sqlite3.Error as e:
                textutil.log(f"[SERVER] ⚠️ Couldn't clear a room in history.db ({e})")


# ---------------------------------------------------------------- 😂 reactions

def room_of(message_id):
    """Which room a message was posted in, or None if there's no such message (or no database)."""
    with _lock:
        connection = _open()
        if connection is None:
            return None
        row = connection.execute("SELECT room FROM messages WHERE id = ?", (message_id,)).fetchone()
    return row[0] if row else None


def reaction_counts(message_ids):
    """{message id: {emoji: how many}} for the messages that have reactions."""
    if not message_ids:
        return {}
    marks = ", ".join("?" * len(message_ids))
    with _lock:
        connection = _open()
        if connection is None:
            return {}
        rows = connection.execute(f"SELECT message_id, emoji, COUNT(*) FROM reactions WHERE message_id IN ({marks}) "
                                  "GROUP BY message_id, emoji ORDER BY MIN(rowid)", list(message_ids)).fetchall()
    counts = {}
    for message_id, emoji, count in rows:
        counts.setdefault(message_id, {})[emoji] = count
    return counts


def search(rooms, word, limit):
    """🔎 Messages in these rooms whose text contains `word` (any case), newest first: [(room, time, name, text)].
    % and _ in the word are plain letters (LIKE would read them as wildcards)."""
    if not rooms:
        return []
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    marks = ", ".join("?" * len(rooms))
    with _lock:
        connection = _open()
        if connection is None:
            return []
        return connection.execute(f"SELECT room, time, name, text FROM messages WHERE room IN ({marks}) "
                                  "AND text LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?",
                                  [*rooms, f"%{escaped}%", limit]).fetchall()


def reactors(message_ids):
    """{message id: set of the logins who reacted to it} (any emoji), for the question of the day's votes."""
    if not message_ids:
        return {}
    marks = ", ".join("?" * len(message_ids))
    with _lock:
        connection = _open()
        if connection is None:
            return {}
        rows = connection.execute(f"SELECT DISTINCT message_id, login FROM reactions WHERE message_id IN ({marks})",
                                  list(message_ids)).fetchall()
    found = {}
    for message_id, login in rows:
        found.setdefault(message_id, set()).add(login)
    return found


def toggle_reaction(message_id, login, emoji):
    """Add this person's emoji to the message, or take it back if it's already there. Returns the new counts."""
    with _lock:
        connection = _open()
        if connection is None:
            return {}
        key = (message_id, login, emoji)
        try:
            if connection.execute("SELECT 1 FROM reactions WHERE message_id = ? AND login = ? AND emoji = ?",
                                  key).fetchone():
                connection.execute("DELETE FROM reactions WHERE message_id = ? AND login = ? AND emoji = ?", key)
            else:
                connection.execute("INSERT INTO reactions (message_id, login, emoji) VALUES (?, ?, ?)", key)
            connection.commit()
        except sqlite3.Error as e:
            connection.rollback()   # never leave a half-done change on the shared connection
            textutil.log(f"[SERVER] ⚠️ Couldn't save a reaction in history.db ({e})")
    return reaction_counts([message_id]).get(message_id, {})


# ---------------------------------------------------------------- ✏️ edit and delete

def message_info(message_id):
    """(room, author login, seconds since it was sent) of a saved message, or None."""
    with _lock:
        connection = _open()
        if connection is None:
            return None
        row = connection.execute("SELECT room, login, created FROM messages WHERE id = ?", (message_id,)).fetchone()
    return (row[0], row[1], time.time() - (row[2] or 0)) if row else None


def change_message(message_id, text):
    """Edit a message's text (it's marked as edited), or delete it (text=None) with its reactions."""
    with _lock:
        connection = _open()
        if connection is None:
            return
        try:
            if text is None:
                connection.execute("DELETE FROM reactions WHERE message_id = ?", (message_id,))
                connection.execute("DELETE FROM messages WHERE id = ?", (message_id,))
            else:
                connection.execute("UPDATE messages SET text = ?, edited = 1 WHERE id = ?", (text, message_id))
            connection.commit()
        except sqlite3.Error as e:
            connection.rollback()
            textutil.log(f"[SERVER] ⚠️ Couldn't change a message in history.db ({e})")
