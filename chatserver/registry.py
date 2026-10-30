"""
📋 The @command decorator: every /command registers itself here, and /help lists them
in the order they were registered.

To add a /command: write a function in the right cmd_*.py and decorate it, like

    @registry.command("/hug", "/hug name", "send a hug 🤗", "💬 Chat")
    def cmd_hug(client, args):
        client.say("🤗")

It shows up in /help by itself. For a new /help section, make a new cmd_*.py file
and add it to commands.py.
"""

COMMANDS = {}


def command(name, usage, description, category):
    def register(function):
        COMMANDS[name] = (function, usage, description, category)
        return function
    return register
