"""
🛡️ Group admin commands.
"""
import time

from chatserver import bank_log, history, registry, rooms, state, storage, wars


# ----- 🛡️ Group admin

def admin_target(client, args, owner_only=False, must_be_member=True):
    """Checks for every admin command. Returns (group key, group, target) or None."""
    key, group = rooms.current_group(client)
    if group is None:
        return None
    allowed = client.key == group["owner"] if owner_only else rooms.is_admin(group, client.key)
    if not allowed:
        client.say("👑 Only the owner can do that." if owner_only else "🛡️ Only group admins can do that.",
                   "error")
        return None
    name = args.split()[0] if args.split() else ""
    target = rooms.find_account(name) if name else None
    if target is None:
        client.say(f"❓ No user called {name or '...'}.", "error")
        return None
    if target == client.key:
        client.say("🙃 You can't do that to yourself.", "error")
        return None
    if target == group["owner"]:
        client.say("👑 You can't do that to the owner.", "error")
        return None
    if target in group["admins"] and client.key != group["owner"]:
        client.say("🛡️ Only the owner can do that to another admin.", "error")
        return None
    if must_be_member and target not in group["members"]:
        client.say(f"❓ {rooms.nick(target)} isn't in this group.", "error")
        return None
    return key, group, target


def remove_from_group(key, group, target):
    group["members"].remove(target)
    if target in group["admins"]:
        group["admins"].remove(target)
    if target in state.online and state.online[target].room == key:
        rooms.move_to_room(state.online[target], "lobby")
    rooms.send_room_list(target)


@registry.command("/kick", "/kick name", "remove from group", "🛡️ Group admin")
def cmd_kick(client, args):
    found = admin_target(client, args)
    if found:
        key, group, target = found
        remove_from_group(key, group, target)
        storage.save_data()
        rooms.tell(target, f"👢 You were kicked from {rooms.room_title(key)} by {rooms.shown(client.key)}.", "error")
        rooms.notify_room(key, f"👢 {rooms.shown(target)} was kicked by {rooms.shown(client.key)}")


@registry.command("/ban", "/ban name", "kick + can't come back", "🛡️ Group admin")
def cmd_ban(client, args):
    found = admin_target(client, args, must_be_member=False)
    if found:
        key, group, target = found
        if target in group["members"]:
            remove_from_group(key, group, target)
        if target in group["requests"]:
            group["requests"].remove(target)
        if target not in group["banned"]:
            group["banned"].append(target)
        storage.save_data()
        rooms.tell(target, f"🔨 You were banned from {rooms.room_title(key)}.", "error")
        rooms.notify_room(key, f"🔨 {rooms.shown(target)} was banned by {rooms.shown(client.key)}")


@registry.command("/unban", "/unban name", "allow back in", "🛡️ Group admin")
def cmd_unban(client, args):
    found = admin_target(client, args, must_be_member=False)
    if found:
        key, group, target = found
        if target not in group["banned"]:
            client.say(f"{rooms.nick(target)} isn't banned.")
            return
        group["banned"].remove(target)
        storage.save_data()
        client.say(f"🕊️ {rooms.shown(target)} is unbanned.")


@registry.command("/mute", "/mute name [minutes]", "silence someone (default 5)", "🛡️ Group admin")
def cmd_mute(client, args):
    found = admin_target(client, args)
    if found:
        key, group, target = found
        parts = args.split()
        minutes = int(parts[1]) if len(parts) > 1 and parts[1].isdecimal() else 5
        minutes = max(1, min(minutes, 1440))
        state.mutes[(key, target)] = time.time() + minutes * 60
        rooms.notify_room(key, f"🔇 {rooms.shown(target)} was muted for {minutes} min by {rooms.shown(client.key)}")
        if target not in state.online or state.online[target].room != key:
            rooms.tell(target, f"🔇 You were muted in {rooms.room_title(key)} for {minutes} min.", "error")


@registry.command("/unmute", "/unmute name", "let them talk again", "🛡️ Group admin")
def cmd_unmute(client, args):
    found = admin_target(client, args)
    if found:
        key, group, target = found
        state.mutes.pop((key, target), None)
        rooms.notify_room(key, f"🔊 {rooms.shown(target)} can talk again")


@registry.command("/promote", "/promote name", "make admin (owner)", "🛡️ Group admin")
def cmd_promote(client, args):
    found = admin_target(client, args, owner_only=True)
    if found:
        key, group, target = found
        if target in group["admins"]:
            client.say(f"{rooms.nick(target)} is already an admin.")
            return
        group["admins"].append(target)
        storage.save_data()
        rooms.notify_room(key, f"🛡️ {rooms.shown(target)} is now an admin of {rooms.room_title(key)}")
        rooms.tell(target, f"🛡️ You're now an admin of {rooms.room_title(key)}!", "event")


@registry.command("/demote", "/demote name", "remove admin (owner)", "🛡️ Group admin")
def cmd_demote(client, args):
    found = admin_target(client, args, owner_only=True)
    if found:
        key, group, target = found
        if target not in group["admins"]:
            client.say(f"{rooms.nick(target)} isn't an admin.")
            return
        group["admins"].remove(target)
        storage.save_data()
        rooms.notify_room(key, f"⬇️ {rooms.shown(target)} is no longer an admin")


@registry.command("/disband", "/disband", "delete your group (owner)", "🛡️ Group admin")
def cmd_disband(client, args):
    key, group = rooms.current_group(client)
    if group is None:
        return
    if client.key != group["owner"]:
        client.say("👑 Only the owner can disband the group.", "error")
        return
    title = rooms.room_title(key)
    for member in group["members"]:
        rooms.tell(member, f"💥 {title} was disbanded by its owner.", "event")
    if group["bank"]:
        state.accounts[client.key]["tokens"] += group["bank"]
        client.say(f"🏦 The group bank's {group['bank']} 🪙 went to you.", "money")
    for c in list(state.online.values()):
        if c.room == key:
            c.room = "lobby"
            rooms.send_history(c, "lobby")
            c.send(rooms.topic_packet("lobby"))   # 📌 the gone group's banner goes, the lobby's (if any) comes
    members = list(group["members"])
    del state.groups[key]
    history.delete_room(key)
    bank_log.forget(key)
    state.polls.pop(key, None)
    wars.forget_group(key)
    for member in members:
        rooms.send_room_list(member)
    for mute in [m for m in state.mutes if m[0] == key]:
        del state.mutes[mute]
    storage.save_data()
