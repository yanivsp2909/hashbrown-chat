"""
💬 What happens with each line someone types, and with files.
"""
import os
import time

from chatserver import achievements, config, hashbrown_ai, matches, registry, rooms, state, storage, textutil


def handle_file(client, msg):
    target = rooms.find_online(client, textutil.clean_text(msg.get("to", "")))
    if target is None:
        return
    if target == client.key:
        client.say("🙃 You can't send a file to yourself.", "error")
        return
    data = msg.get("data")
    if not isinstance(data, str) or len(data) > config.MAX_FILE_B64:
        client.say("📁 Files must be 2 MB or less.", "error")
        return
    filename = os.path.basename(textutil.clean_text(msg.get("filename", "")).replace("\\", "/"))[:100] or "file"
    state.online[target].send({"type": "file", "from": rooms.nick(client.key), "filename": filename, "data": data})
    client.say(f"📤 Sent {filename} ({len(data) * 3 // 4 // 1024 + 1} KB) to {rooms.shown(target)}.")

def post_chat(client, text, action=False):
    """Send a chat line to the client's room. Returns False if they're muted."""
    room = client.room
    until = state.mutes.get((room, client.key), 0)
    if until > time.time():
        client.say(f"🔇 You're muted here for {int((until - time.time()) // 60) + 1} more min.", "error")
        return False
    account = state.accounts[client.key]
    msg = rooms.chat_message(account["nick"], account["badge"], text, action)
    state.history[room].append(msg)
    rooms.send_room(room, msg)  # the sender gets it too, so they see their own line with the time
    textutil.log(f"[{room}] {account['nick']}: {text}")
    account["messages"] += 1
    if account["messages"] >= 100:
        achievements.unlock(client.key, "chatty")
    return True

def check_quiz(client, text):
    if state.quiz and client.room == "lobby" and text.strip() == state.quiz["answer"] and client.key not in state.matches:
        state.accounts[client.key]["tokens"] += state.quiz["reward"]
        rooms.notify_room("lobby", f"🎉 {rooms.shown(client.key)} got it first! {state.quiz['answer']} is right, "
                             f"+{state.quiz['reward']} 🪙", kind="event")
        state.quiz = None
        storage.save_data()

def handle_line(client, text):
    text = text.strip()
    if not text:
        return
    match = state.matches.get(client.key)
    if match and not text.startswith("/") and match.game.looks_like_move(text):
        matches.do_move(client, text)  # in a game, "5" or "c3 d4" or "w" is a move, not chat
        return
    if text.startswith("/"):
        name, _, args = text.partition(" ")
        entry = registry.COMMANDS.get(name.lower())
        if entry is None:
            client.say(f"❓ Unknown command {name}. Type /help", "error")
            return
        entry[0](client, args.strip())
        return
    if not post_chat(client, text):
        return
    if text.lower().startswith("@hashbrown"):
        hashbrown_ai.ask_hashbrown(client, text[len("@hashbrown"):].lstrip(" ,:"))
    check_quiz(client, text)
