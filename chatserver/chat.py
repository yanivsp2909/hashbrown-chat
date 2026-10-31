"""
💬 What happens with each line someone types, and with files.
"""
import os
import time

from chatserver import (achievements, config, drawing, group_stocks, hashbrown_ai, hashbrown_extras, history,
                        matches, offers, profiles, quests, registry, rooms, state, storage, textutil)


def handle_file(client, msg):
    target = rooms.find_online(client, textutil.clean_text(msg.get("to", "")))
    if target is None:
        return
    if target == client.key:
        client.say("🙃 You can't send a file to yourself.", "error")
        return
    refusal = profiles.dm_refusal(client.key, target)   # 👤 their "who can send me things" setting
    if refusal:
        client.say(refusal, "error")
        return
    data = msg.get("data")
    if not isinstance(data, str) or len(data) > config.MAX_FILE_B64:
        client.say("📁 Files must be 2 MB or less.", "error")
        return
    filename = os.path.basename(textutil.clean_text(msg.get("filename", "")).replace("\\", "/"))[:100] or "file"
    packet = {"type": "file", "from": rooms.nick(client.key), "filename": filename, "data": data}
    if offers.wants_offers(target):   # 📎 ask first; the file waits here until they /accept
        offers.make(client.key, target, filename, len(data) * 3 // 4, packet=packet)
        return
    state.online[target].send(packet)
    client.say(f"📤 Sent {filename} ({len(data) * 3 // 4 // 1024 + 1} KB) to {rooms.shown(target)}.")


def post_chat(client, text, action=False):
    """Send a chat line to the client's room. Returns False if they're muted."""
    room = client.room
    until = state.mutes.get((room, client.key), 0)
    if until > time.time():
        client.say(f"🔇 You're muted here for {int((until - time.time()) // 60) + 1} more min.", "error")
        return False
    account = state.accounts[client.key]
    msg = {**rooms.chat_message(account["nick"], account["badge"], text, action), **profiles.looks(account)}
    history.add(room, msg, client.key)  # gives msg its "id"
    rooms.send_room(room, msg)  # the sender gets it too, so they see their own line with the time
    client.is_typing, client.last_typing = False, 0.0   # ⌨️ the message ends "typing" (the others hide it)
    textutil.log(f"[{room}] {account['nick']}: {text}")
    account["messages"] += 1
    group_stocks.note_message(room, client.key)   # 👥📈 a busy group's stock goes up
    quests.bump(client.key, "chat")
    if account["messages"] >= 100:
        achievements.unlock(client.key, "chatty")
    return True


def check_quiz(client, text):
    if (state.quiz and client.room == "lobby" and text.strip() == state.quiz["answer"]
            and client.key not in state.matches):
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
    if drawing.check_guess(client, text):   # 🎨 the drawing's word: checked here, never posted
        return
    if not post_chat(client, text):
        return
    if text.lower().startswith("@hashbrown"):
        hashbrown_ai.ask_hashbrown(client, text[len("@hashbrown"):].lstrip(" ,:"))
    check_quiz(client, text)
    hashbrown_extras.check_trivia(client, text)


def react(client, msg):
    """😂 {"type": "react", "id": message id, "emoji": "👍"}: toggle your reaction, and tell the room."""
    message_id, emoji = msg.get("id"), msg.get("emoji")
    room = history.room_of(message_id) if isinstance(message_id, int) and not isinstance(message_id, bool) else None
    if emoji not in config.REACTIONS or room is None or not rooms.is_member(client.key, room):
        client.say("😶 Can't react to that.", "error")
        return
    counts = history.toggle_reaction(message_id, client.key, emoji)
    rooms.send_room(room, {"type": "reactions", "id": message_id, "counts": counts})


def change(client, msg):
    """✏️ {"type": "edit", "id", "text"} or 🗑️ {"type": "delete", "id"}: only your own, only for EDIT_MINUTES."""
    message_id = msg.get("id")
    valid_id = isinstance(message_id, int) and not isinstance(message_id, bool)
    info = history.message_info(message_id) if valid_id else None
    if info is None:
        client.say("✏️ Can't find that message.", "error")
        return
    room, author, age = info
    if room != client.room or state.mutes.get((room, client.key), 0) > time.time():
        client.say("✏️ You can only change messages in the room you're in (and not while muted).", "error")
        return
    if author != client.key:
        client.say("✏️ You can only edit or delete your own messages.", "error")
        return
    if age > config.EDIT_MINUTES * 60:
        client.say(f"✏️ That message is too old to change ({config.EDIT_MINUTES} minutes).", "error")
        return
    if msg.get("type") == "delete":
        history.change_message(message_id, None)
        rooms.send_room(room, {"type": "deleted", "id": message_id})
        return
    text = textutil.clean_text(msg.get("text", "")).strip()[:config.MAX_TEXT]
    if not text:
        client.say("✏️ The new text is empty. To remove a message, delete it.", "error")
        return
    history.change_message(message_id, text)
    rooms.send_room(room, {"type": "edited", "id": message_id, "text": text})
