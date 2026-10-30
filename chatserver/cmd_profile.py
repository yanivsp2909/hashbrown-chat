"""
👤 Profile commands: /profile [name], /setprofile field value, /password old new.
"""
from chatserver import auth, profiles, registry, rooms, state


@registry.command("/profile", "/profile [name]", "someone's profile card 👤 (yours without a name)", "👤 Profile")
def cmd_profile(client, args):
    key = rooms.find_account(args.strip()) if args.strip() else client.key
    if key is None:
        client.say(f"❓ No one called {args.strip()}.", "error")
        return
    client.say(profiles.card_text(key, client.key))


@registry.command("/setprofile", "/setprofile field value", "change your profile (avatar, bio, status...)", "👤 Profile")
def cmd_setprofile(client, args):
    field, _, value = args.strip().partition(" ")
    field = field.lower()
    if field == "name":   # the display name is /nick
        registry.COMMANDS["/nick"][0](client, value)
        return
    if field == "badge":
        registry.COMMANDS["/badge"][0](client, value)
        return
    ok, text = profiles.set_field(client.key, field, value)
    client.say(text, "system" if ok else "error")
    if ok and "profiles" in client.features:
        client.send({"type": "profile", "mine": True, "profile": profiles.mine(client.key)})


@registry.command("/password", "/password old new", "change your password (the old one first) 🔑", "👤 Profile")
def cmd_password(client, args):
    parts = args.split()
    if len(parts) != 2:
        client.say("🔑 Use: /password oldpassword newpassword", "error")
        return
    profiles.change_password(client, parts[0], parts[1], auth.check_password)


def get_profile(client, msg):
    """The website's {"type": "get_profile", "name"} -> {"type": "profile", "profile"}."""
    name = msg.get("name")
    key = rooms.find_account(name) if isinstance(name, str) and name.strip() else None
    if key is None:
        client.say(f"❓ No one called {str(name)[:16]}.", "error")
        return
    client.send({"type": "profile", "mine": key == client.key,
                 "profile": profiles.mine(key) if key == client.key else profiles.public(key, client.key)})
