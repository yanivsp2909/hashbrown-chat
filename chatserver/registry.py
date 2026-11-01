"""
📋 The @command decorator: every /command registers itself here, and /help lists them
in the order they were registered.

To add a /command: write a function in the right cmd_*.py and decorate it, like

    @registry.command("/hug", "/hug name", "send a hug 🤗", "💬 Chat")
    def cmd_hug(client, args):
        client.say("🤗")

It shows up in /help by itself. For a new /help section, make a new cmd_*.py file
and add it to commands.py.

👥 A command that acts on a group (/kick, /bank...) says group_only=True: it then works only in that group's
chat (or from a Groups screen button for that group), and /help shows it only there. chat.handle_line checks.
"""

COMMANDS = {}
GROUP_ONLY = set()             # 👥 names of the commands that act on a group
GROUP_FIELD_OK = {"/pin"}      # 👥 may come with a "group" field too (the Groups screen's buttons): + GROUP_ONLY


def command(name, usage, description, category, group_only=False):
    def register(function):
        COMMANDS[name] = (function, usage, description, category)
        if group_only:
            GROUP_ONLY.add(name)
            GROUP_FIELD_OK.add(name)
        return function
    return register
