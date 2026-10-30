"""
🥔 Hashbrown chat server: accounts, groups, tokens, casino, games, files and an AI bot.

Run:   python server.py        (games.py and the chatserver/ folder must be next to it)
Code:  chatserver/, one topic per file. Settings (ports, prices, ADMIN_PASSWORD...): chatserver/config.py
Saves: chat_data.json next to this file (accounts, tokens, groups survive restarts)
AI:    fill in hashbrown_config.json (created on first run) to wake up Hashbrown
Type   help   in this window for server console commands.
"""
from chatserver.connections import main


if __name__ == "__main__":
    main()
