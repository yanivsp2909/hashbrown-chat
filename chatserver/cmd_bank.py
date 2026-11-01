"""
🏦 Group bank commands.
"""
import unicodedata

from chatserver import achievements, bank_log, config, registry, rooms, state, storage, textutil


# ----- 🏦 Group bank

@registry.command("/bank", "/bank", "the group's bank and upgrades", "🏦 Group bank", group_only=True)
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


@registry.command("/donate", "/donate amount", "put your tokens in the group bank", "🏦 Group bank", group_only=True)
def cmd_donate(client, args):
    key, group = rooms.current_group(client)
    if group is None:
        return
    amount = rooms.parse_amount(client, args)
    if amount is None:
        return
    state.accounts[client.key]["tokens"] -= amount
    group["bank"] += amount
    bank_log.record(key, "donate", client.key, amount)
    rooms.notify_room(key, f"🤝 {rooms.shown(client.key)} donated {amount} 🪙 to the bank "
                           f"(now {group['bank']} 🪙)", kind="money")
    if amount >= config.TEAM_PLAYER_DONATION:  # a 1-token donation shouldn't earn a 50-token achievement
        achievements.unlock(client.key, "team_player")
    storage.save_data()


@registry.command("/upgrade", "/upgrade name", "buy an upgrade with the bank (admins)", "🏦 Group bank", group_only=True)
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
    bank_log.record(key, "upgrade", client.key, -price, name)
    storage.save_data()
    rooms.notify_room(key, f"⬆️ {rooms.shown(client.key)} bought {icon} {name}: {what}!", kind="event")
    if name == "emoji":
        client.say("🎨 Now pick it: /groupemoji 🔥")


@registry.command("/groupemoji", "/groupemoji emoji", "set the group emoji (needs 🎨)", "🏦 Group bank", group_only=True)
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
    for member in group["members"]:   # the room's name changed in everyone's chat switcher
        rooms.send_room_list(member)
    storage.save_data()
    rooms.notify_room(key, f"🎨 The group is now {rooms.room_title(key)}", kind="event")


@registry.command("/personality", "/personality text", "how Hashbrown acts in this group (🎭 upgrade)",
                  "🏦 Group bank", group_only=True)
def cmd_personality(client, args):
    key, group = rooms.current_group(client)
    if group is None:
        return
    if not rooms.is_admin(group, client.key):
        client.say("🎭 Only group admins can set Hashbrown's personality.", "error")
        return
    if "personality" not in group["upgrades"]:
        client.say("🎭 This needs the 🎭 personality upgrade first: /upgrade personality", "error")
        return
    text = textutil.clean_text(args).strip()[:config.PERSONALITY_MAX]
    group["personality"] = text or None   # empty: back to the normal Hashbrown
    storage.save_data()
    rooms.notify_room(key, f"🎭 Hashbrown's personality here: {text}" if text else "🎭 Hashbrown is back to normal here.",
                      kind="event")


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
