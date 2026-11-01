"""
⚔️ Group war commands: /war group (declare), /war accept group, /war (the score).
"""
import time

from chatserver import config, registry, rooms, state, wars


@registry.command("/war", "/war [group | accept group]", "your group vs another group ⚔️", "⚔️ Group wars", group_only=True)
def cmd_war(client, args):
    parts = args.split()
    if not parts:
        war = wars.war_of(rooms.group_context(client))   # (a Groups screen button: that group)
        client.say(wars.score_text(war) if war else "⚔️ This room isn't at war. A group admin can type /war group.")
        return
    key, group = rooms.current_group(client)
    if group is None:
        return
    if not rooms.is_admin(group, client.key):
        client.say("⚔️ Only group admins can start or accept a war.", "error")
        return
    if parts[0].lower() == "accept" and len(parts) == 2:
        accept(client, key, parts[1].lower())
    else:
        declare(client, key, parts[0].lower())


def declare(client, key, target):
    if target == key:
        client.say("⚔️ You can't declare war on your own group!", "error")
        return
    if target not in state.groups:
        client.say(f"❓ No group called {target}. See /groups", "error")
        return
    if wars.war_of(key) or wars.war_of(target):
        client.say("⚔️ One of these groups is already at war. Wait for it to end.", "error")
        return
    state.war_invites[target] = (key, time.time())
    other = state.groups[target]
    for admin in [other["owner"]] + other["admins"]:
        rooms.tell(admin, f"⚔️ {rooms.room_title(key)} declared war on {rooms.room_title(target)}! "
                          f"An admin types /war accept {state.groups[key]['name']} within "
                          f"{config.WAR_ACCEPT_MINUTES} min.", "event")
    client.say(f"⚔️ War declared on {rooms.room_title(target)}. Waiting for them to accept.")


def accept(client, key, attacker):
    invite = state.war_invites.get(key)
    if not invite or invite[0] != attacker or time.time() - invite[1] > config.WAR_ACCEPT_MINUTES * 60:
        client.say("⚔️ That group didn't declare war on you (or it was too long ago).", "error")
        return
    del state.war_invites[key]
    if attacker not in state.groups or wars.war_of(key) or wars.war_of(attacker):
        client.say("⚔️ That war can't start now.", "error")
        return
    wars.start_war(attacker, key)
