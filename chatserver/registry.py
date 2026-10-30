"""
📋 The @command decorator: every /command registers itself here, and /help lists them
in the order they were registered.
"""

# ---------------------------------------------------------------- commands
# @command registers a function as a /command and puts it in /help automatically.

COMMANDS = {}

def command(name, usage, description, category):
    def register(function):
        COMMANDS[name] = (function, usage, description, category)
        return function
    return register
