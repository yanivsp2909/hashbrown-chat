"""
💬 Chat commands.
"""
from datetime import datetime

from chatserver import chat, config, registry, rooms, state, storage


# ----- 💬 Chat

@registry.command("/help", "/help", "show this list", "💬 Chat")
def cmd_help(client, args):
    by_category = {}
    for function, usage, description, category in registry.COMMANDS.values():
        by_category.setdefault(category, []).append(f"  {usage:<32} {description}")
    lines = ["📖 COMMANDS"]
    for category, items in by_category.items():
        lines.append(f"\n{category}")
        lines += items
    lines.append("\nAnything that isn't a command is a chat message to the room you're in.")
    lines.append(f"🥔 Start a message with @hashbrown to ask the AI ({config.HASHBROWN_COST} 🪙).")
    client.say("\n".join(lines), "help")


@registry.command("/users", "/users", "who's online and where", "💬 Chat")
def cmd_users(client, args):
    lines = [f"🟢 Online now ({len(state.online)}):"]
    for key in sorted(state.online, key=lambda k: rooms.nick(k).lower()):
        playing = "  🎮 playing" if key in state.matches else ""
        lines.append(f"  {rooms.shown(key)}  {rooms.room_title(state.online[key].room)}{playing}")
    client.say("\n".join(lines))


@registry.command("/send", "/send name message", "private message 💌", "💬 Chat")
def cmd_send(client, args):
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        client.say("Usage: /send name message", "error")
        return
    offline = rooms.find_account(parts[0])
    if offline is not None and offline not in state.online:
        keep_for_later(client, offline, parts[1])
        return
    target = rooms.find_online(client, parts[0])
    if target is None:
        return
    if target == client.key:
        client.say("🙃 You can't message yourself.", "error")
        return
    stamp = datetime.now().strftime("%H:%M")
    rooms.tell(target, f"💌 [{stamp}] {rooms.shown(client.key)} → you: {parts[1]}", "private")
    client.say(f"💌 [{stamp}] you → {rooms.shown(target)}: {parts[1]}", "private")


def keep_for_later(client, target, text):
    """📬 They're offline: keep the message, it's delivered when they log in."""
    inbox = state.accounts[target]["inbox"]
    if len(inbox) >= config.OFFLINE_MAX:
        client.say(f"📬 {rooms.nick(target)}'s inbox is full. Try again when they're online.", "error")
        return
    inbox.append({"from": rooms.shown(client.key), "time": datetime.now().strftime("%H:%M"), "text": text})
    storage.save_data()
    client.say(f"📬 {rooms.nick(target)} is offline. They'll get your message when they log in.")


@registry.command("/me", "/me action", "act it out: * Yaniv dances", "💬 Chat")
def cmd_me(client, args):
    if args:
        chat.post_chat(client, args, action=True)


@registry.command("/nick", "/nick newname", "change your display name", "💬 Chat")
def cmd_nick(client, args):
    new = args.strip()
    if not rooms.valid_name(new):
        client.say(f"❌ Names: {rooms.NAME_RULE}", "error")
        return
    owner = rooms.find_account(new)
    login_owner = new.lower() if new.lower() in state.accounts else None
    if (owner and owner != client.key) or (login_owner and login_owner != client.key):
        client.say("❌ Someone already has that name.", "error")
        return
    old = rooms.nick(client.key)
    state.accounts[client.key]["nick"] = new
    storage.save_data()
    rooms.notify_room(client.room, f"✏️ {old} is now called {rooms.shown(client.key)}")
    client.say(f"(You still log in as {state.accounts[client.key]['login']}.)")


@registry.command("/whois", "/whois name", "someone's profile", "💬 Chat")
def cmd_whois(client, args):
    key = rooms.find_account(args.strip()) if args.strip() else client.key
    if key is None:
        client.say(f"❓ No one called {args.strip()}.", "error")
        return
    a = state.accounts[key]
    status = f"🟢 online in {rooms.room_title(state.online[key].room)}" if key in state.online else "⚫ offline"
    member_of = [g["name"] for g in state.groups.values() if key in g["members"]]
    client.say(f"👤 {rooms.shown(key)}\n"
               f"   🪙 {a['tokens']} tokens   🏆 {a['wins']}W {a['losses']}L {a['draws']}D   📈 ELO {a['elo']}\n"
               f"   {status}\n"
               f"   👥 groups: {', '.join(member_of) or 'none'}\n"
               f"   📅 joined {a['joined']}   🔥 daily streak: {a['streak']}\n"
               f"   🏅 badges: {' '.join(a['badges']) or 'none'}   "
               f"achievements: {len(a['achievements'])}/{len(config.ACHIEVEMENTS)}")


@registry.command("/quit", "/quit", "leave the chat", "💬 Chat")
def cmd_quit(client, args):
    client.quitting = True
