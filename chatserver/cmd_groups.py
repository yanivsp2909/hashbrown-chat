"""
👥 Group commands.
"""
import time

from chatserver import achievements, config, history, registry, rooms, state, storage


@registry.command("/groups", "/groups", "list all groups", "👥 Groups")
def cmd_groups(client, args):
    if not state.groups:
        client.say(f"No groups yet. Make one: /create name  (costs {config.GROUP_COST} 🪙)")
        return
    lines = ["👥 Groups:"]
    for key in sorted(state.groups):
        g = state.groups[key]
        here = sum(1 for m in g["members"] if m in state.online)
        mine = "  ✅ member" if client.key in g["members"] else ""
        lines.append(f"  {rooms.room_title(key)}  👥 {len(g['members'])} members, {here} online{mine}")
    lines.append("🔒 = private (needs approval). Join with /join name")
    client.say("\n".join(lines))


@registry.command("/create", "/create name [private]", f"new group ({config.GROUP_COST} 🪙)", "👥 Groups")
def cmd_create(client, args):
    parts = args.split()
    if not parts:
        client.say("Usage: /create name   or   /create name private", "error")
        return
    name, key = parts[0], parts[0].lower()
    private = len(parts) > 1 and parts[1].lower() in ("private", "p")
    if not rooms.valid_name(name) or key == "lobby":
        client.say(f"❌ Group names: {rooms.NAME_RULE}", "error")
        return
    if key in state.groups:
        client.say("❌ That group already exists.", "error")
        return
    if sum(1 for g in state.groups.values() if g["owner"] == client.key) >= config.MAX_OWNED_GROUPS:
        client.say(f"👑 You can own at most {config.MAX_OWNED_GROUPS} groups. /disband one first.", "error")
        return
    account = state.accounts[client.key]
    if account["tokens"] < config.GROUP_COST:
        client.say(f"💸 Creating a group costs {config.GROUP_COST} 🪙, you have {account['tokens']}.", "error")
        return
    account["tokens"] -= config.GROUP_COST
    state.groups[key] = storage.new_group(name, client.key, private)
    history.delete_room(key)  # start clean, whatever an old group with this name left behind
    client.say(f"🎉 Created {rooms.room_title(key)} for {config.GROUP_COST} 🪙. You're the owner 👑\n"
               f"🏦 The group bank earns {config.GROUP_INCOME} 🪙/min while a member is online. See /bank", "event")
    rooms.announce(f"✨ New group: {rooms.room_title(key)} by {rooms.shown(client.key)}", exclude={client.key})
    rooms.move_to_room(client, key)
    achievements.unlock(client.key, "founder")
    storage.save_data()


@registry.command("/join", "/join name", "enter a group (or ask to)", "👥 Groups")
def cmd_join(client, args):
    name = args.strip()
    if not name:
        client.say("Usage: /join name   (see /groups)", "error")
        return
    if name.lower() == "lobby":
        cmd_lobby(client, "")
        return
    key = name.lower()
    group = state.groups.get(key)
    if group is None:
        client.say(f"❓ No group called {name}. See /groups", "error")
        return
    if client.key in group["banned"]:
        client.say(f"🚫 You're banned from {rooms.room_title(key)}.", "error")
        return
    if client.key in group["members"]:
        if client.room == key:
            client.say("You're already here.")
        else:
            rooms.move_to_room(client, key)
        return
    if not group["private"]:
        group["members"].append(client.key)
        storage.save_data()
        rooms.move_to_room(client, key)
        return
    if client.key in group["requests"]:
        client.say("⏳ Your request is still waiting for an admin.")
        return
    group["requests"].append(client.key)
    storage.save_data()
    client.say(f"📨 Request sent! An admin of {rooms.room_title(key)} has to approve you.")
    for admin in [group["owner"]] + group["admins"]:
        rooms.tell(admin, f"📨 {rooms.shown(client.key)} wants to join {rooms.room_title(key)}.  "
                          f"In its chat: /approve {rooms.nick(client.key)}  or  /reject {rooms.nick(client.key)}",
                   "event")


@registry.command("/lobby", "/lobby", "go back to the lobby", "👥 Groups")
def cmd_lobby(client, args):
    if client.room == "lobby":
        client.say("You're already in the lobby.")
    else:
        rooms.move_to_room(client, "lobby")


@registry.command("/leave", "/leave", "quit the group you're in", "👥 Groups", group_only=True)
def cmd_leave(client, args):
    key, group = rooms.current_group(client)
    if group is None:
        return
    if client.key == group["owner"]:
        client.say("👑 You own this group. Use /disband to delete it.", "error")
        return
    group["members"].remove(client.key)
    if client.key in group["admins"]:
        group["admins"].remove(client.key)
    storage.save_data()
    if client.room == key:   # (a Groups screen button from another room: you stay where you are)
        rooms.move_to_room(client, "lobby")
    else:
        rooms.send_room_list(client.key)
    client.say(f"👋 You left {rooms.room_title(key)}.")


@registry.command("/members", "/members", "who's in this group", "👥 Groups", group_only=True)
def cmd_members(client, args):
    key, group = rooms.current_group(client)
    if group is None:
        return
    lines = [f"👥 {rooms.room_title(key)}:"]
    for member in group["members"]:
        role = "👑 owner" if member == group["owner"] else "🛡️ admin" if member in group["admins"] else ""
        status = "🟢" if member in state.online else "⚫"
        muted = " 🔇" if state.mutes.get((key, member), 0) > time.time() else ""
        lines.append(f"  {status} {rooms.shown(member)} {role}{muted}")
    client.say("\n".join(lines))


@registry.command("/requests", "/requests", "join requests (admins)", "👥 Groups", group_only=True)
def cmd_requests(client, args):
    key, group = rooms.current_group(client)
    if group is None:
        return
    if not rooms.is_admin(group, client.key):
        client.say("🛡️ Only group admins can see requests.", "error")
        return
    if not group["requests"]:
        client.say("📭 No one is waiting to join.")
        return
    names = ", ".join(rooms.nick(k) for k in group["requests"])
    client.say(f"📨 Waiting: {names}\nUse /approve name or /reject name")


def request_target(client, args, command):
    """For /approve and /reject (in the group's chat): returns (group key, group, user) or None."""
    parts = args.split()
    if not parts:
        client.say(f"Usage: {command} name", "error")
        return None
    key, group = rooms.current_group(client)
    if group is None:
        return None
    if len(parts) > 1 and parts[1].lower() != key:   # the old "/approve name group", for another group
        client.say(f"👥 Open the group's chat to use {command}", "error")
        return None
    if not rooms.is_admin(group, client.key):
        client.say("🛡️ Only group admins can do that.", "error")
        return None
    target = rooms.find_account(parts[0])
    if target not in group["requests"]:
        client.say(f"❓ {parts[0]} didn't ask to join {rooms.room_title(key)}.", "error")
        return None
    return key, group, target


@registry.command("/approve", "/approve name", "let someone in (admins)", "👥 Groups", group_only=True)
def cmd_approve(client, args):
    found = request_target(client, args, "/approve")
    if found is None:
        return
    key, group, target = found
    group["requests"].remove(target)
    group["members"].append(target)
    storage.save_data()
    rooms.send_room_list(target)
    rooms.tell(target, f"✅ You were accepted into {rooms.room_title(key)}! Type /join {group['name']}", "event")
    client.say(f"✅ {rooms.shown(target)} can now join.")
    rooms.notify_room(key, f"🎉 {rooms.shown(target)} is now a member of {rooms.room_title(key)}", exclude=client)


@registry.command("/reject", "/reject name", "turn down a request (admins)", "👥 Groups", group_only=True)
def cmd_reject(client, args):
    found = request_target(client, args, "/reject")
    if found is None:
        return
    key, group, target = found
    group["requests"].remove(target)
    storage.save_data()
    rooms.tell(target, f"❌ Your request to join {rooms.room_title(key)} was turned down.", "error")
    client.say(f"❌ Rejected {rooms.shown(target)}.")
