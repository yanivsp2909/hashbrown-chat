"""
🤝 Friend commands (the rules are in friends.py).
"""
from chatserver import friends, registry, rooms, storage

ACTIONS = {"add": friends.ask, "remove": friends.remove, "accept": friends.accept, "decline": friends.decline}
USAGE = "Usage: /friend add name  (or remove, accept, decline)"


@registry.command("/friend", "/friend add name", "ask someone to be friends 🤝 (also: remove, accept, decline)",
                  "🤝 Friends")
def cmd_friend(client, args):
    parts = args.split()
    if len(parts) < 2 or parts[0].lower() not in ACTIONS:
        client.say(USAGE, "error")
        return
    target = rooms.find_account(parts[1])
    if target is None:
        client.say(f"❓ No user called {parts[1]}.", "error")
        return
    if ACTIONS[parts[0].lower()](client, target):
        storage.save_data()


@registry.command("/friends", "/friends", "your friends, where they are, and who asked 🤝", "🤝 Friends")
def cmd_friends(client, args):
    client.say(friends.lines(client.key))
