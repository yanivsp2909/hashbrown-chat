"""
🌐 Accepting connections and talking to each client, from login to goodbye.
"""
import os
import signal
import socket
import threading
import time
import traceback

from chatserver import (auth, background, chat, config, discovery, group_view, hashbrown_ai, matches, offers, receipts,
                        resume, rooms,
                        session, state, storage, textutil, transfers, website)
from chatserver import commands  # noqa: F401  (registers the commands, in /help order)
from chatserver import cmd_profile, netmap, profiles


# ---------------------------------------------------------------- connections

def disconnect(client):
    try:
        with state.lock:
            key = client.key
            if key and state.online.get(key) is client:
                rooms.end_typing(client)
                del state.online[key]
                state.accounts[key]["last_seen"] = time.time()   # 👤 "last seen" on profiles
                if client.quitting or client.no_resume:
                    resume.forget(key)       # /quit or kicked: no coming back with the token
                else:
                    resume.went_away(client)   # 🔁 a drop: they may reconnect and catch up
                group_view.mark_dirty()   # 👥 one fewer online
                match = state.matches.get(key)
                if match:
                    matches.finish_match(match, match.opponent(key), f"{rooms.nick(key)} disconnected")
                state.invites.pop(key, None)
                matches.stop_watching(key)
                offers.drop_all_of(key)   # (before the transfers: a waiting big file is cancelled with a reason)
                transfers.drop_all_of(key)
                state.solo.pop(key, None)
                for waiting in state.invites.values():
                    waiting[:] = [i for i in waiting if i["from"] != key]
                rooms.notify_room(client.room, f"👋 {rooms.shown(key)} left the chat")
                textutil.log(f"[SERVER] {rooms.nick(key)} disconnected")
                storage.save_data()
    except Exception:
        textutil.log("[SERVER] Error while disconnecting:\n" + traceback.format_exc())
    finally:
        client.close()  # always, or the socket and its writer thread would stay open forever


def handle_client(sock, address):
    """Runs in its own thread, one per connection."""
    with state.lock:
        too_many = state.connections >= config.MAX_CONNECTIONS
        if not too_many:
            state.connections += 1
    if too_many:
        textutil.log(f"[SERVER] ⚠️ Too many connections ({config.MAX_CONNECTIONS}), turned away {address}")
        sock.close()
        return
    try:
        talk_to(sock, address)
    finally:
        with state.lock:
            state.connections -= 1


def try_auth(client, msg):
    """handle_auth(), but a bug in it answers "something went wrong" instead of dropping the person."""
    try:
        return auth.handle_auth(client, msg)
    except Exception:
        textutil.log("[SERVER] Error while logging someone in:\n" + traceback.format_exc())
        client.send({"type": "auth_result", "ok": False, "text": "💥 Something went wrong. Try again."})
        return False


def answer_ping(client, msg):
    """{"type": "ping", "t": 123.4} -> {"type": "pong", "t": 123.4}: the client times the round trip."""
    now = time.time()
    while client.pings and now - client.pings[0] > 1:
        client.pings.popleft()
    if len(client.pings) >= config.PINGS_PER_SECOND:
        return
    client.pings.append(now)
    t = msg.get("t")
    has_number = isinstance(t, (int, float)) and not isinstance(t, bool)
    client.send({"type": "pong", **({"t": t} if has_number else {})})


def pass_on_typing(client, stopped=False):
    """⌨️ Tell the others in the room (the clients that asked for it) that this person is typing, or stopped.
    No more than TYPING_LIMIT of these in TYPING_WINDOW seconds, so switching on and off can't flood the room."""
    if stopped != client.is_typing:
        return   # a stop without a start (or a start while already typing: keep_typing decides those)
    now = time.time()
    while client.typing_times and now - client.typing_times[0] > config.TYPING_WINDOW:
        client.typing_times.popleft()
    if not stopped and len(client.typing_times) >= config.TYPING_LIMIT:
        return   # (a stop always goes: there's never more of them than starts)
    client.typing_times.append(now)
    if not stopped:
        client.last_typing = now
    client.is_typing = not stopped
    note = {"type": "typing_stop" if stopped else "typing", "name": rooms.nick(client.key)}
    for other in list(state.online.values()):
        if other is not client and other.room == client.room and "typing" in other.features:
            other.send({**note, "room": client.room} if "rooms" in other.features else note)


def keep_typing(client):
    """A "typing" packet: the first one starts it; while typing, it's a refresh (limited to TYPING_EVERY)."""
    if not client.is_typing:
        pass_on_typing(client)
    elif time.time() - client.last_typing >= config.TYPING_EVERY:
        client.is_typing = False      # passed on again as a fresh "typing"
        pass_on_typing(client)


BIG_FILE_PACKETS = {"file_start": transfers.start, "file_chunk": transfers.chunk, "file_cancel": transfers.cancel}


def handle_message(client, msg):
    """A message from someone who is logged in. Called while holding the lock."""
    try:
        kind = msg.get("type")
        if kind == "ping":       # 🏓 not chat, so it skips the spam limit (it has its own)
            answer_ping(client, msg)
            return
        if kind == "typing":     # ⌨️ the same: its own small limit
            keep_typing(client)
            return
        client.types_in[str(kind)[:20]] += 1   # 🗺️ (the network map counts types, never content)
        if kind in ("get_netmap", "netmap_closed", "probe_back"):   # 🗺️ the live network map: no spam limit
            netmap.handle(client, msg)
            return
        if kind in ("get_groups", "get_group", "groups_closed"):   # 👥 the website's Groups screen
            if kind == "groups_closed" or rooms.spam_ok(client):
                group_view.handle(client, msg)
            return
        if kind in ("get_profile", "change_password"):   # 👤 the website's profile card / edit screen
            if rooms.spam_ok(client):
                if kind == "get_profile":
                    cmd_profile.get_profile(client, msg)
                elif isinstance(msg.get("old"), str) and isinstance(msg.get("new"), str):
                    profiles.change_password(client, msg["old"], msg["new"], auth.check_password)
            return
        if kind == "seen":       # ✓✓ the same: one per private message at most
            receipts.seen(client, msg)
            return
        if kind == "typing_stop":
            pass_on_typing(client, stopped=True)
            return
        if kind in BIG_FILE_PACKETS:   # 📦 big files: not counted as spam, the acks slow them down
            BIG_FILE_PACKETS[kind](client, msg)
            return
        if kind == "react":      # 😂 counts toward the spam limit like a message
            if rooms.spam_ok(client):
                chat.react(client, msg)
            return
        if kind in ("edit", "delete"):   # ✏️ 🗑️ the same
            if rooms.spam_ok(client):
                chat.change(client, msg)
            return
        text = textutil.clean_text(msg.get("text", ""))[:config.MAX_TEXT]
        if not matches.is_game_move(client, text) and not rooms.spam_ok(client):
            return  # game moves don't count as spam
        if text.startswith("/"):
            group_view.mark_dirty()   # 👥 a command may have changed a group: open Groups screens refresh
        if msg.get("type") == "line":
            chat.handle_line(client, text)
        elif msg.get("type") == "file":
            chat.handle_file(client, msg)
    except Exception:  # a bug in one command must not kick the person out
        textutil.log("[SERVER] Error while handling a message:\n" + traceback.format_exc())
        client.say("💥 Something went wrong on the server with that. Try something else.", "error")


def talk_to(sock, address):
    """Read one connection's messages until it closes."""
    try:
        client = session.Client(sock, address)
    except RuntimeError:  # couldn't start its writer thread
        sock.close()
        return
    failed_logins = 0
    try:
        for raw in session.recv_lines(sock, client):
            msg = session.parse_message(raw)
            if msg is None:
                continue
            if client.key is None:  # not logged in yet (or replaced by a newer login): only auth
                if msg.get("type") != "auth":
                    continue
                if try_auth(client, msg):
                    sock.settimeout(None)  # logged in: no more time limit
                    continue
                failed_logins += 1
                if failed_logins >= 5:
                    client.say("🚫 Too many failed attempts. Bye.", "error")
                    break
                continue
            with state.lock:
                if client.key is not None:
                    handle_message(client, msg)
            if client.quitting:
                break
    except OSError:
        pass  # connection dropped or timed out (ConnectionResetError and timeouts are OSErrors)
    finally:
        disconnect(client)


def start_server(host=config.HOST, port=config.PORT, run_loops=True, run_console=True):
    """Load the data, wake Hashbrown, start the helper threads and open the port.
    Returns the listening socket, or None if the server can't start.
    (The tests call this with port 0 and without the loops and the console.)"""
    if not storage.load_data():
        return None
    state.hashbrown = hashbrown_ai.load_hashbrown()
    password = config.admin_password()   # never print the password itself, not even its length
    if password == config.DEFAULT_ADMIN_PASSWORD:
        textutil.log("[SERVER] 🔒 /admin is off. To turn it on, save a password in the Mac Keychain as "
                     "\"hashbrown-admin\" (start.sh loads it) or set the HASHBROWN_ADMIN_PASSWORD environment variable.")
    elif len(password) < config.ADMIN_PASSWORD_WARN_UNDER:
        textutil.log(f"[SERVER] ⚠️ The admin password is shorter than {config.ADMIN_PASSWORD_WARN_UNDER} characters. "
                     "It works, but a longer one is much harder to guess.")
    loops = (([background.income_loop, background.quiz_loop, background.qotd_loop,
                background.offers_loop, background.groups_loop, background.netmap_loop] if run_loops else [])
             + ([background.console_loop] if run_console else []))
    for loop in loops:
        threading.Thread(target=loop, daemon=True).start()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name != "nt":  # on Windows this option would let two servers share the port by accident
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((host, port))
    except OSError as e:
        textutil.log(f"[SERVER] ❌ Can't use port {port} ({e}). Is the server already running in another window?")
        server_socket.close()
        return None
    server_socket.listen()
    textutil.log(f"[SERVER] 💬 Chat server running on port {server_socket.getsockname()[1]} (Ctrl+C to stop)")
    return server_socket


def serve_forever(server_socket):
    """Accept connections until Ctrl+C (or until the socket is closed). Everyone gets their own thread."""
    server_socket.settimeout(config.ACCEPT_WAKEUP)  # wake up now and then, so Ctrl+C works on Windows too
    try:
        while True:
            try:
                sock, address = server_socket.accept()
            except socket.timeout:
                continue
            except OSError as e:
                if server_socket.fileno() == -1:  # the socket was closed: time to stop
                    break
                # e.g. someone gave up halfway through connecting: just carry on
                textutil.log(f"[SERVER] ⚠️ Couldn't accept a connection ({e}). Still running.")
                time.sleep(0.1)
                continue
            try:
                threading.Thread(target=handle_client, args=(sock, address), daemon=True).start()
            except RuntimeError:  # the computer can't start more threads right now
                textutil.log("[SERVER] ⚠️ Too many threads, turned a connection away.")
                sock.close()
    except KeyboardInterrupt:
        textutil.log("\n[SERVER] Shutting down.")
    finally:
        with state.lock:
            background.run_safely(matches.end_all_matches)  # nobody loses their bet because the server stopped
        storage.save_data()
        server_socket.close()


def stop_on_sigterm(*_):
    """Closing the window or a "stop" button sends SIGTERM: shut down like Ctrl+C (save, refund, stop the website)."""
    raise KeyboardInterrupt


def main():
    signal.signal(signal.SIGTERM, stop_on_sigterm)
    server_socket = start_server()
    if server_socket is None:
        return
    web = website.start_website(config.PORT)
    finder = discovery.start_discovery()   # lets client.py find this server without typing an IP
    try:
        serve_forever(server_socket)
    finally:
        website.stop_website(web)
        if finder is not None:
            finder.close()
