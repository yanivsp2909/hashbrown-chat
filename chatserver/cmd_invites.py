"""
📨 Group invite commands (the rules are in invites.py).
"""
from chatserver import invites, registry, rooms, state, storage


@registry.command("/invite", "/invite name", "invite someone to this group, even a private one (admins) 📨",
                  "👥 Groups", group_only=True)
def cmd_invite(client, args):
    key, group = rooms.current_group(client)
    if group is None:
        return
    if not rooms.is_admin(group, client.key):
        client.say("🛡️ Only group admins can invite.", "error")
        return
    name = args.split()[0] if args.split() else ""
    if not name:
        client.say("Usage: /invite name", "error")
        return
    target = rooms.find_account(name)
    if target is None:
        client.say(f"❓ No user called {name}.", "error")
        return
    if invites.invite(client, key, group, target):
        storage.save_data()


@registry.command("/invites", "/invites [decline group]", "your group invites 📨 (/join group accepts one)", "👥 Groups")
def cmd_invites(client, args):
    parts = args.split()
    if parts and parts[0].lower() == "decline":
        decline(client, parts[1] if len(parts) > 1 else "")
        return
    waiting = invites.mine(client.key)
    if not waiting:
        client.say("📭 No group invites right now.")
        return
    lines = ["📨 Your group invites:"]
    for key, group, invite in waiting:
        lines.append(f"  {rooms.room_title(key)} from {rooms.shown(invite['by'])} "
                     f"({invites.hours_left(invite)} h left)   /join {group['name']}  or  /invites decline {group['name']}")
    client.say("\n".join(lines))


def decline(client, name):
    key = name.lower()
    group = state.groups.get(key)
    if group is None:
        client.say("Usage: /invites decline group" if not name else f"❓ No group called {name}.", "error")
        return
    if invites.decline(client, key, group):
        storage.save_data()

