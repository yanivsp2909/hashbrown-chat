"""
🥔 Hashbrown chat server: accounts, groups, tokens, casino, games, files and an AI bot.

Run:   python server.py        (games.py must be in the same folder)
Saves: chat_data.json next to this file (accounts, tokens, groups survive restarts)
AI:    fill in hashbrown_config.json (created on first run) to wake up Hashbrown
Type   help   in this window for server console commands.
"""
import os
import random
import secrets
import socket
import threading
import time
import traceback
import unicodedata
from collections import deque
from datetime import datetime

import games

from chatserver import achievements, auth, background, chat, config, hashbrown_ai, matches, registry, rooms, session, state, storage, textutil


GAMES = {"ttt": games.TicTacToe, "tictactoe": games.TicTacToe,
         "checkers": games.Checkers, "damka": games.Checkers,
         "math": games.MathDuel, "mathduel": games.MathDuel}

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
    target = rooms.find_online(client, parts[0])
    if target is None:
        return
    if target == client.key:
        client.say("🙃 You can't message yourself.", "error")
        return
    stamp = datetime.now().strftime("%H:%M")
    rooms.tell(target, f"💌 [{stamp}] {rooms.shown(client.key)} → you: {parts[1]}", "private")
    client.say(f"💌 [{stamp}] you → {rooms.shown(target)}: {parts[1]}", "private")

@registry.command("/me", "/me action", "act it out: * Yaniv dances", "💬 Chat")
def cmd_me(client, args):
    if args:
        chat.post_chat(client, args, action=True)

@registry.command("/nick", "/nick newname", "change your display name", "💬 Chat")
def cmd_nick(client, args):
    new = args.strip()
    if not rooms.valid_name(new):
        client.say("❌ Names: 3-16 letters, numbers or _", "error")
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
               f"   🪙 {a['tokens']} tokens   🏆 {a['wins']}W {a['losses']}L {a['draws']}D\n"
               f"   {status}\n"
               f"   👥 groups: {', '.join(member_of) or 'none'}\n"
               f"   📅 joined {a['joined']}   🔥 daily streak: {a['streak']}\n"
               f"   🏅 badges: {' '.join(a['badges']) or 'none'}   "
               f"achievements: {len(a['achievements'])}/{len(config.ACHIEVEMENTS)}")

@registry.command("/quit", "/quit", "leave the chat", "💬 Chat")
def cmd_quit(client, args):
    client.quitting = True

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
        client.say("❌ Group names: 3-16 letters, numbers or _", "error")
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
    state.history[key] = deque(maxlen=config.HISTORY_SIZE)
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
                    f"/approve {rooms.nick(client.key)} {group['name']}  or  /reject {rooms.nick(client.key)} {group['name']}",
             "event")

@registry.command("/lobby", "/lobby", "go back to the lobby", "👥 Groups")
def cmd_lobby(client, args):
    if client.room == "lobby":
        client.say("You're already in the lobby.")
    else:
        rooms.move_to_room(client, "lobby")

@registry.command("/leave", "/leave", "quit the group you're in", "👥 Groups")
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
    rooms.move_to_room(client, "lobby")
    client.say(f"👋 You left {rooms.room_title(key)}.")

@registry.command("/members", "/members", "who's in this group", "👥 Groups")
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

@registry.command("/requests", "/requests", "join requests (admins)", "👥 Groups")
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

def request_target(client, args):
    """For /approve and /reject: returns (group key, group, user) or None."""
    parts = args.split()
    if not parts:
        client.say("Usage: /approve name [group]", "error")
        return None
    key = parts[1].lower() if len(parts) > 1 else client.room
    group = state.groups.get(key)
    if group is None:
        client.say("❓ Which group? Use /approve name group", "error")
        return None
    if not rooms.is_admin(group, client.key):
        client.say("🛡️ Only group admins can do that.", "error")
        return None
    target = rooms.find_account(parts[0])
    if target not in group["requests"]:
        client.say(f"❓ {parts[0]} didn't ask to join {rooms.room_title(key)}.", "error")
        return None
    return key, group, target

@registry.command("/approve", "/approve name [group]", "let someone in (admins)", "👥 Groups")
def cmd_approve(client, args):
    found = request_target(client, args)
    if found is None:
        return
    key, group, target = found
    group["requests"].remove(target)
    group["members"].append(target)
    storage.save_data()
    rooms.tell(target, f"✅ You were accepted into {rooms.room_title(key)}! Type /join {group['name']}", "event")
    client.say(f"✅ {rooms.shown(target)} can now join.")
    rooms.notify_room(key, f"🎉 {rooms.shown(target)} is now a member of {rooms.room_title(key)}", exclude=client)

@registry.command("/reject", "/reject name [group]", "turn down a request (admins)", "👥 Groups")
def cmd_reject(client, args):
    found = request_target(client, args)
    if found is None:
        return
    key, group, target = found
    group["requests"].remove(target)
    storage.save_data()
    rooms.tell(target, f"❌ Your request to join {rooms.room_title(key)} was turned down.", "error")
    client.say(f"❌ Rejected {rooms.shown(target)}.")

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
            c.send({"type": "history", "room": rooms.room_title("lobby"), "messages": list(state.history["lobby"])})
    del state.groups[key]
    del state.history[key]
    for mute in [m for m in state.mutes if m[0] == key]:
        del state.mutes[mute]
    storage.save_data()

# ----- 🏦 Group bank

@registry.command("/bank", "/bank", "the group's bank and upgrades", "🏦 Group bank")
def cmd_bank(client, args):
    key, group = rooms.current_group(client)
    if group is None:
        return
    online_members = sum(1 for m in group["members"] if m in state.online)
    lines = [f"🏦 {rooms.room_title(key)} bank: {group['bank']} 🪙",
             f"   earns {config.GROUP_INCOME} 🪙/min while a member is online ({online_members} online now)",
             "⬆️ Upgrades:"]
    for name, (icon, price, what) in config.GROUP_UPGRADES.items():
        status = "✅ owned" if name in group["upgrades"] else f"{price} 🪙"
        lines.append(f"  {icon} {name:<10} {status:<10} {what}")
    lines.append("Admins buy with /upgrade name.  Anyone can chip in with /donate amount.")
    client.say("\n".join(lines), "money")

@registry.command("/donate", "/donate amount", "put your tokens in the group bank", "🏦 Group bank")
def cmd_donate(client, args):
    key, group = rooms.current_group(client)
    if group is None:
        return
    amount = rooms.parse_amount(client, args)
    if amount is None:
        return
    state.accounts[client.key]["tokens"] -= amount
    group["bank"] += amount
    rooms.notify_room(key, f"🤝 {rooms.shown(client.key)} donated {amount} 🪙 to the bank (now {group['bank']} 🪙)",
                kind="money")
    if amount >= config.TEAM_PLAYER_DONATION:  # a 1-token donation shouldn't earn a 50-token achievement
        achievements.unlock(client.key, "team_player")
    storage.save_data()

@registry.command("/upgrade", "/upgrade name", "buy an upgrade with the bank (admins)", "🏦 Group bank")
def cmd_upgrade(client, args):
    key, group = rooms.current_group(client)
    if group is None:
        return
    name = args.strip().lower()
    if name not in config.GROUP_UPGRADES:
        cmd_bank(client, "")
        return
    if not rooms.is_admin(group, client.key):
        client.say("🛡️ Only group admins can spend the bank.", "error")
        return
    icon, price, what = config.GROUP_UPGRADES[name]
    if name in group["upgrades"]:
        client.say(f"{icon} {rooms.room_title(key)} already has that.")
        return
    if group["bank"] < price:
        client.say(f"💸 {icon} {name} costs {price} 🪙, the bank has {group['bank']}.", "error")
        return
    group["bank"] -= price
    group["upgrades"].append(name)
    if name == "history":
        state.history[key] = deque(state.history[key], maxlen=config.BIG_HISTORY_SIZE)
    storage.save_data()
    rooms.notify_room(key, f"⬆️ {rooms.shown(client.key)} bought {icon} {name}: {what}!", kind="event")
    if name == "emoji":
        client.say("🎨 Now pick it: /groupemoji 🔥")

@registry.command("/groupemoji", "/groupemoji emoji", "set the group emoji (needs 🎨)", "🏦 Group bank")
def cmd_groupemoji(client, args):
    key, group = rooms.current_group(client)
    if group is None:
        return
    if not rooms.is_admin(group, client.key):
        client.say("🛡️ Only group admins can do that.", "error")
        return
    if "emoji" not in group["upgrades"]:
        client.say("🎨 Buy the emoji upgrade first: /upgrade emoji", "error")
        return
    emoji = args.strip()
    # Only emoji pieces: symbols (So, Sk) plus the invisible joiners and variation marks (Mn, Cf)
    if not emoji or len(emoji) > 8 or any(unicodedata.category(ch) not in ("So", "Sk", "Mn", "Cf")
                                          for ch in emoji):
        client.say("🎨 Send a single emoji, like /groupemoji 🔥", "error")
        return
    group["emoji"] = emoji
    storage.save_data()
    rooms.notify_room(key, f"🎨 The group is now {rooms.room_title(key)}", kind="event")

@registry.command("/topgroups", "/topgroups", "richest groups", "🏦 Group bank")
def cmd_topgroups(client, args):
    if not state.groups:
        client.say("No groups yet.")
        return
    ranking = sorted(state.groups, key=lambda k: state.groups[k]["bank"], reverse=True)[:10]
    lines = ["🏦 Richest groups:"]
    for i, key in enumerate(ranking, 1):
        g = state.groups[key]
        lines.append(f"  {i}. {rooms.room_title(key)}  {g['bank']} 🪙  ⬆️ {len(g['upgrades'])} upgrades")
    client.say("\n".join(lines), "money")

# ----- 🪙 Tokens

@registry.command("/balance", "/balance [name]", "how many tokens 🪙", "🪙 Tokens")
def cmd_balance(client, args):
    key = rooms.find_account(args.strip()) if args.strip() else client.key
    if key is None:
        client.say(f"❓ No one called {args.strip()}.", "error")
        return
    client.say(f"🪙 {rooms.shown(key)} has {state.accounts[key]['tokens']} tokens.", "money")

@registry.command("/top", "/top", "richest players 🏆", "🪙 Tokens")
def cmd_top(client, args):
    ranking = sorted(state.accounts, key=lambda k: state.accounts[k]["tokens"], reverse=True)[:10]
    medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
    lines = ["🏆 Richest players:"]
    for medal, key in zip(medals, ranking):
        lines.append(f"  {medal} {rooms.shown(key)}  {state.accounts[key]['tokens']} 🪙")
    client.say("\n".join(lines), "money")

@registry.command("/give", "/give name amount", "send tokens to someone", "🪙 Tokens")
def cmd_give(client, args):
    parts = args.split()
    if len(parts) != 2:
        client.say("Usage: /give name amount", "error")
        return
    target = rooms.find_account(parts[0])
    if target is None or target == client.key:
        client.say("❓ Give to who?", "error")
        return
    amount = rooms.parse_amount(client, parts[1])
    if amount is None:
        return
    state.accounts[client.key]["tokens"] -= amount
    state.accounts[target]["tokens"] += amount
    client.say(f"🎁 You gave {amount} 🪙 to {rooms.shown(target)}.", "money")
    rooms.tell(target, f"🎁 {rooms.shown(client.key)} gave you {amount} 🪙!", "money")
    achievements.check_rich(target)
    storage.save_data()

@registry.command("/daily", "/daily", "free tokens every day, more for streaks 🔥", "🪙 Tokens")
def cmd_daily(client, args):
    account = state.accounts[client.key]
    since = time.time() - account["last_daily"]
    if since < 20 * 3600:
        wait = 20 * 3600 - since
        client.say(f"⏳ Come back in {int(wait // 3600)}h {int(wait % 3600 // 60)}m. "
                   f"🔥 Streak: {account['streak']} days", "error")
        return
    # Claim again within 48 hours to keep the streak going
    account["streak"] = account["streak"] + 1 if since < 48 * 3600 else 1
    reward = min(config.DAILY_BONUS + config.STREAK_BONUS * (account["streak"] - 1), config.DAILY_MAX)
    account["last_daily"] = time.time()
    account["tokens"] += reward
    tomorrow = min(reward + config.STREAK_BONUS, config.DAILY_MAX)
    client.say(f"🎁 +{reward} 🪙 daily bonus!  🔥 {account['streak']} day streak\n"
               f"   Come back in 20-48 hours for {tomorrow} 🪙 (wait longer and the streak resets).", "money")
    if account["streak"] >= 7:
        achievements.unlock(client.key, "on_fire")
    achievements.check_rich(client.key)
    storage.save_data()

@registry.command("/rob", "/rob name", "40% chance to steal, or pay a fine 🦹", "🪙 Tokens")
def cmd_rob(client, args):
    target = rooms.find_online(client, args.strip())
    if target is None:
        return
    if target == client.key:
        client.say("🙃 Robbing yourself? Bold.", "error")
        return
    wait = state.last_rob.get(client.key, 0) + 300 - time.time()
    if wait > 0:
        client.say(f"🚓 Lay low for {int(wait // 60)}m {int(wait % 60)}s before robbing again.", "error")
        return
    victim, robber = state.accounts[target], state.accounts[client.key]
    if victim["tokens"] < 50:
        client.say(f"🤷 {rooms.nick(target)} is too broke to rob.", "error")
        return
    state.last_rob[client.key] = time.time()
    if random.random() < 0.4:
        stolen = min(500, max(1, victim["tokens"] * random.randint(5, 15) // 100))
        victim["tokens"] -= stolen
        robber["tokens"] += stolen
        client.say(f"🦹 Success! You stole {stolen} 🪙 from {rooms.shown(target)}.", "money")
        rooms.tell(target, f"🚨 {rooms.shown(client.key)} robbed you and got away with {stolen} 🪙!", "error")
        achievements.unlock(client.key, "bandit")
        achievements.check_rich(client.key)
    else:
        fine = min(50, robber["tokens"])
        robber["tokens"] -= fine
        victim["tokens"] += fine
        client.say(f"🚓 Caught! You paid {fine} 🪙 to {rooms.shown(target)}.", "error")
        rooms.tell(target, f"🛡️ {rooms.shown(client.key)} tried to rob you and failed. You got {fine} 🪙!", "money")
    storage.save_data()

@registry.command("/shop", "/shop", "badges for your name", "🪙 Tokens")
def cmd_shop(client, args):
    owned = state.accounts[client.key]["badges"]
    lines = ["🛒 Badge shop (shows next to your name):"]
    for badge, price in config.SHOP.items():
        lines.append(f"  {badge}  {price} 🪙{'  ✅ owned' if badge in owned else ''}")
    lines.append("Buy with /buy 🔥   Switch with /badge 😎   Hide with /badge off")
    client.say("\n".join(lines), "money")

@registry.command("/buy", "/buy badge", "buy a badge from /shop", "🪙 Tokens")
def cmd_buy(client, args):
    badge = args.strip()
    account = state.accounts[client.key]
    if badge not in config.SHOP:
        client.say("❓ That's not in the /shop. Copy the emoji exactly.", "error")
        return
    if badge in account["badges"]:
        client.say("You already own it. Wear it with /badge " + badge)
        return
    if account["tokens"] < config.SHOP[badge]:
        client.say(f"💸 {badge} costs {config.SHOP[badge]} 🪙, you have {account['tokens']}.", "error")
        return
    account["tokens"] -= config.SHOP[badge]
    account["badges"].append(badge)
    account["badge"] = badge
    storage.save_data()
    client.say(f"🛍️ You bought {badge}! You're now {rooms.shown(client.key)}", "money")
    if config.SHOP[badge] >= 1000:
        rooms.announce(f"💸 {rooms.shown(client.key)} just bought the {badge} badge!", exclude={client.key})

@registry.command("/badge", "/badge emoji|off", "wear a badge you own", "🪙 Tokens")
def cmd_badge(client, args):
    choice = args.strip()
    account = state.accounts[client.key]
    if choice == "off":
        account["badge"] = ""
    elif choice in account["badges"]:
        account["badge"] = choice
    else:
        client.say(f"You don't own that. Yours: {' '.join(account['badges']) or 'none, see /shop'}", "error")
        return
    storage.save_data()
    client.say(f"✨ You're now {rooms.shown(client.key)}")

# ----- 🎰 Casino

def gamble_result(client, bet, payout, text, game):
    """payout = total tokens returned (0 = lost the bet)."""
    account = state.accounts[client.key]
    account["tokens"] += payout - bet
    net = payout - bet
    if net > 0:
        outcome = f"🎉 You won {net} 🪙!"
    elif net == 0:
        outcome = "😐 You got your bet back."
    else:
        outcome = f"😢 You lost {bet} 🪙."
    client.say(f"{text}\n{outcome}  Balance: {account['tokens']} 🪙", "money" if net >= 0 else "error")
    if net >= 500:
        rooms.announce(f"🎰💥 {rooms.shown(client.key)} just won {net} 🪙 on {game}!", exclude={client.key})
    if bet >= 500:
        achievements.unlock(client.key, "high_roller")
    achievements.check_rich(client.key)
    storage.save_data()

@registry.command("/coinflip", "/coinflip amount heads|tails", "double or nothing", "🎰 Casino")
def cmd_coinflip(client, args):
    parts = args.split()
    if len(parts) != 2 or parts[1].lower() not in ("heads", "tails", "h", "t"):
        client.say("Usage: /coinflip amount heads   (or tails)", "error")
        return
    bet = rooms.parse_amount(client, parts[0])
    if bet is None:
        return
    guess = "heads" if parts[1].lower().startswith("h") else "tails"
    side = random.choice(["heads", "tails"])
    gamble_result(client, bet, bet * 2 if side == guess else 0, f"🪙 The coin spins... {side.upper()}!", "coinflip")

@registry.command("/dice", "/dice amount", "2 dice vs the house 🎲", "🎰 Casino")
def cmd_dice(client, args):
    bet = rooms.parse_amount(client, args)
    if bet is None:
        return
    faces = "⚀⚁⚂⚃⚄⚅"
    you = [random.randint(1, 6) for _ in range(2)]
    house = [random.randint(1, 6) for _ in range(2)]
    text = (f"🎲 You: {faces[you[0] - 1]} {faces[you[1] - 1]} = {sum(you)}   "
            f"House: {faces[house[0] - 1]} {faces[house[1] - 1]} = {sum(house)}")
    payout = bet * 2 if sum(you) > sum(house) else bet if sum(you) == sum(house) else 0
    gamble_result(client, bet, payout, text, "dice")

@registry.command("/slots", "/slots amount", "3 same = x10, 💎💎💎 = x25", "🎰 Casino")
def cmd_slots(client, args):
    bet = rooms.parse_amount(client, args)
    if bet is None:
        return
    reels = random.choices(config.SLOT_SYMBOLS, k=3)
    if reels == ["💎"] * 3:
        multiplier = 25
    elif len(set(reels)) == 1:
        multiplier = 10
    elif len(set(reels)) == 2:
        multiplier = 1.5
    else:
        multiplier = 0
    gamble_result(client, bet, int(bet * multiplier), f"🎰 [ {' | '.join(reels)} ]", "slots")
    if multiplier >= 10:
        achievements.unlock(client.key, "jackpot")
        storage.save_data()  # gamble_result already saved, before this achievement

@registry.command("/games", "/games", "what you can play", "🎮 Games")
def cmd_games(client, args):
    client.say("🎮 Games (1v1, optional token bet):\n"
               "  ❌⭕ ttt        Tic-Tac-Toe\n"
               "  🔴🔵 damka      Checkers (also: checkers)\n"
               "  ➗   math       Math duel: first to 3 right answers\n"
               "Challenge: /challenge name game [bet]   e.g.  /challenge Adi damka 100\n\n"
               "🟩 Solo: /wordle  guess the word, win up to 60 🪙", "game")

@registry.command("/challenge", "/challenge name game [bet]", "invite to a 1v1", "🎮 Games")
def cmd_challenge(client, args):
    parts = args.split()
    if len(parts) < 2:
        client.say("Usage: /challenge name game [bet]   games: ttt, damka, math", "error")
        return
    target = rooms.find_online(client, parts[0])
    if target is None:
        return
    game_class = GAMES.get(parts[1].lower())
    if game_class is None:
        client.say("❓ Games: ttt, damka (checkers), math", "error")
        return
    if target == client.key:
        client.say("🙃 You can't challenge yourself.", "error")
        return
    bet = 0
    if len(parts) > 2:
        bet = rooms.parse_amount(client, parts[2])
        if bet is None:
            return
    if client.key in state.matches or target in state.matches:
        client.say("⏳ One of you is already in a game.", "error")
        return
    if state.accounts[target]["tokens"] < bet:
        client.say(f"💸 {rooms.nick(target)} can't afford a {bet} 🪙 bet.", "error")
        return
    waiting = [i for i in state.invites.get(target, []) if i["from"] != client.key]
    waiting.append({"from": client.key, "game": game_class, "bet": bet, "time": time.time()})
    state.invites[target] = waiting
    stake = f" for {bet} 🪙" if bet else ""
    rooms.tell(target, f"⚔️ {rooms.shown(client.key)} challenges you to {game_class.title}{stake}!  "
                 f"/accept {rooms.nick(client.key)}  or  /decline {rooms.nick(client.key)}", "event")
    client.say(f"⚔️ Challenge sent to {rooms.shown(target)}. Waiting for them...")

def pick_invite(client, args):
    fresh = [i for i in state.invites.get(client.key, []) if time.time() - i["time"] < 180]
    state.invites[client.key] = fresh
    if not fresh:
        client.say("📭 No challenges waiting for you.", "error")
        return None
    if args.strip():
        invite = next((i for i in fresh if rooms.nick(i["from"]).lower() == args.strip().lower()), None)
        if invite is None:
            client.say(f"❓ No challenge from {args.strip()}.", "error")
            return None
    else:
        invite = fresh[-1]
    fresh.remove(invite)
    return invite

@registry.command("/accept", "/accept [name]", "accept a challenge", "🎮 Games")
def cmd_accept(client, args):
    invite = pick_invite(client, args)
    if invite is None:
        return
    challenger, bet = invite["from"], invite["bet"]
    if challenger not in state.online:
        client.say("😕 They left already.", "error")
        return
    if challenger in state.matches or client.key in state.matches:
        client.say("⏳ One of you is already in a game.", "error")
        return
    if state.accounts[challenger]["tokens"] < bet or state.accounts[client.key]["tokens"] < bet:
        client.say("💸 Someone can't afford the bet anymore.", "error")
        return
    matches.start_match(invite["game"], challenger, client.key, bet)

@registry.command("/decline", "/decline [name]", "say no to a challenge", "🎮 Games")
def cmd_decline(client, args):
    invite = pick_invite(client, args)
    if invite:
        client.say("👎 Declined.")
        rooms.tell(invite["from"], f"👎 {rooms.shown(client.key)} declined your challenge.", "error")

@registry.command("/move", "/move ...", "a move (or just type it)", "🎮 Games")
def cmd_move(client, args):
    matches.do_move(client, args)

@registry.command("/board", "/board", "show the board again", "🎮 Games")
def cmd_board(client, args):
    match = state.matches.get(client.key)
    if match is None:
        client.say("🎮 You're not in a game.", "error")
        return
    p1, p2 = match.players
    client.send({"type": "msg", "kind": "board", "state": match.game.state(client.key),
                 "text": f"{match.game.title}   {rooms.shown(p1)} vs {rooms.shown(p2)}\n{match.game.render(client.key)}"})

@registry.command("/resign", "/resign", "give up the game 🏳️", "🎮 Games")
def cmd_resign(client, args):
    match = state.matches.get(client.key)
    if match is None:
        client.say("🎮 You're not in a game.", "error")
        return
    matches.finish_match(match, match.opponent(client.key), f"{rooms.nick(client.key)} resigned 🏳️")

# ----- 🟩 Solo: Wordle

def send_wordle(client, game, text):
    client.send({"type": "msg", "kind": "board", "text": text, "state": game.state()})

@registry.command("/wordle", "/wordle", "solo word game, win tokens 🟩", "🎮 Games")
def cmd_wordle(client, args):
    game = state.solo.get(client.key)
    if game and not game.finished:
        send_wordle(client, game, f"{games.Wordle.title} (still going)\n{game.render()}")
        return
    state.solo[client.key] = game = games.Wordle()
    account = state.accounts[client.key]
    left = config.SOLO_MAX_REWARDS - (account["solo_rewarded"] if account["solo_day"] == textutil.today() else 0)
    prize = f"Win up to 60 🪙 ({left} rewarded games left today)" if left > 0 else \
        "No more rewards today, but you can still play for fun"
    send_wordle(client, game, f"{games.Wordle.title}\n📜 {games.Wordle.help}\n🪙 {prize}\n\n{game.render()}")

@registry.command("/g", "/g word", "guess in your Wordle", "🎮 Games")
def cmd_guess(client, args):
    game = state.solo.get(client.key)
    if game is None or game.finished:
        client.say("🟩 Start a game first: /wordle", "error")
        return
    ok, info = game.guess(args)
    if not ok:
        client.say(info, "error")
        return
    send_wordle(client, game, f"\n{game.render()}")
    if not game.finished:
        return
    del state.solo[client.key]
    if not game.won:
        client.say(f"💀 Out of tries! The word was {game.answer.upper()}.", "error")
        return
    account = state.accounts[client.key]
    tries = len(game.guesses)
    if account["solo_day"] != textutil.today():
        account["solo_day"], account["solo_rewarded"] = textutil.today(), 0
    if account["solo_rewarded"] < config.SOLO_MAX_REWARDS:
        account["solo_rewarded"] += 1
        account["tokens"] += game.reward()
        client.say(f"🎉 Solved in {tries}/6! +{game.reward()} 🪙 "
                   f"({account['solo_rewarded']}/{config.SOLO_MAX_REWARDS} rewarded today)", "money")
    else:
        client.say(f"🎉 Solved in {tries}/6! (No more token rewards today.)", "money")
    rooms.announce(f"🟩 {rooms.shown(client.key)} solved Wordle in {tries}/6!\n{game.share()}", exclude={client.key})
    achievements.unlock(client.key, "wordsmith")
    if tries <= 3:
        achievements.unlock(client.key, "genius")
    achievements.check_rich(client.key)
    storage.save_data()

@registry.command("/giveup", "/giveup", "quit your Wordle", "🎮 Games")
def cmd_giveup(client, args):
    game = state.solo.pop(client.key, None)
    if game is None:
        client.say("🟩 You're not playing Wordle.", "error")
        return
    client.say(f"🏳️ The word was {game.answer.upper()}.")

@registry.command("/admin", "/admin password", "become a server admin", "🛠️ Admin")
def cmd_admin(client, args):
    account = state.accounts[client.key]
    if account["admin"]:
        client.say("🛠️ You're already an admin. Try /admintokens")
        return
    password = config.admin_password()
    if password == config.DEFAULT_ADMIN_PASSWORD:
        client.say("🔒 /admin is disabled until the host changes the admin password.", "error")
        return
    # Wrong tries from ALL accounts count together, so making extra accounts doesn't give more guesses
    now = time.time()
    state.admin_fail_times[:] = [t for t in state.admin_fail_times if now - t < config.ADMIN_FAIL_WINDOW]
    if len(state.admin_fail_times) >= config.ADMIN_FAIL_LIMIT:
        client.say("🔒 Too many wrong admin passwords. Try again in 10 minutes.", "error")
        return
    if not secrets.compare_digest(args.strip().encode("utf-8", "replace"), password.encode("utf-8", "replace")):
        state.admin_fail_times.append(now)
        client.say("❌ Wrong admin password.", "error")
        textutil.log(f"[SERVER] ⚠️ {rooms.nick(client.key)} typed a wrong /admin password")
        return
    account["admin"] = True
    storage.save_data()
    client.say("🛠️ You're now an admin! Try /admintokens", "event")
    textutil.log(f"[SERVER] {rooms.nick(client.key)} became an admin")

@registry.command("/admintokens", "/admintokens [name]", f"admin: +{config.ADMIN_TOKENS} 🪙", "🛠️ Admin")
def cmd_admintokens(client, args):
    if not state.accounts[client.key]["admin"]:
        client.say("🛠️ Admins only. Use /admin password first.", "error")
        return
    target = rooms.find_account(args.strip()) if args.strip() else client.key
    if target is None:
        client.say(f"❓ No one called {args.strip()}.", "error")
        return
    state.accounts[target]["tokens"] += config.ADMIN_TOKENS
    client.say(f"🛠️ +{config.ADMIN_TOKENS} 🪙 to {rooms.shown(target)}.", "money")
    if target != client.key:
        rooms.tell(target, f"🎁 An admin gave you {config.ADMIN_TOKENS} 🪙!", "money")
    textutil.log(f"[SERVER] {rooms.nick(client.key)} used /admintokens on {rooms.nick(target)}")
    achievements.check_rich(target)
    storage.save_data()

# ----- 📁 Files

@registry.command("/sendfile", "/sendfile name path", "send a file (up to 2 MB) 📁", "📁 Files")
def cmd_sendfile(client, args):
    client.say("📁 Your client.py is too old for files. Get the new one.", "error")

# ----- 🏅 Achievements

@registry.command("/achievements", "/achievements", "your trophies and how to get the rest", "🪙 Tokens")
def cmd_achievements(client, args):
    owned = state.accounts[client.key]["achievements"]
    lines = [f"🏅 Achievements ({len(owned)}/{len(config.ACHIEVEMENTS)}):"]
    for name, (icon, title, how, reward) in config.ACHIEVEMENTS.items():
        mark = "✅" if name in owned else "🔒"
        lines.append(f"  {mark} {icon} {title:<17} {how}  (+{reward} 🪙)")
    client.say("\n".join(lines), "money")

@registry.command("/ask", "/ask question", f"ask Hashbrown, the AI ({config.HASHBROWN_COST} 🪙)", "🥔 Hashbrown")
def cmd_ask(client, args):
    if chat.post_chat(client, "@hashbrown " + args):
        hashbrown_ai.ask_hashbrown(client, args)

# ---------------------------------------------------------------- connections

def disconnect(client):
    try:
        with state.lock:
            key = client.key
            if key and state.online.get(key) is client:
                del state.online[key]
                match = state.matches.get(key)
                if match:
                    matches.finish_match(match, match.opponent(key), f"{rooms.nick(key)} disconnected")
                state.invites.pop(key, None)
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

def handle_message(client, msg):
    """A message from someone who is logged in. Called while holding the lock."""
    try:
        text = textutil.clean_text(msg.get("text", ""))[:config.MAX_TEXT]
        if not matches.is_game_move(client, text) and not rooms.spam_ok(client):
            return  # game moves don't count as spam
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
    if config.admin_password() == config.DEFAULT_ADMIN_PASSWORD:  # never print the password itself
        textutil.log("[SERVER] 🔒 /admin is off. To turn it on, set the HASHBROWN_ADMIN_PASSWORD environment "
            "variable (or put a password in ADMIN_PASSWORD in server.py).")
    loops = ([background.income_loop, background.quiz_loop] if run_loops else []) + ([background.console_loop] if run_console else [])
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

def main():
    server_socket = start_server()
    if server_socket is not None:
        serve_forever(server_socket)


if __name__ == "__main__":
    main()
