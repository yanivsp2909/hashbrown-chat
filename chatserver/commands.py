"""
📋 Loads every command module. The order here is the order of the sections in /help.
(Only this file imports the cmd_* modules: importing one earlier would change /help.)
A new cmd_*.py file does nothing until it's listed here.
"""
from chatserver import (  # noqa: F401  (importing them is what registers the commands)
    cmd_chat,
    cmd_groups,
    cmd_group_admin,
    cmd_bank,
    cmd_tokens,
    cmd_casino,
    cmd_games,
    cmd_admin,
    cmd_files,
    cmd_ask,
)
