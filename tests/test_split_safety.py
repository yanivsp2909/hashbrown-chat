"""
🧱 Safety checks for moving server.py's code into the chatserver/ package (Phase 2).
These must stay true no matter which file the code lives in.
"""
import os

import server
from chatserver import config

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
HELP_SNAPSHOT = os.path.join(HERE, "data", "help.txt")


def test_help_is_exactly_the_saved_snapshot(user):
    adi = user("Adi")
    adi.line("/help")
    text = adi.expect(lambda m: m.get("kind") == "help")["text"]
    with open(HELP_SNAPSHOT, encoding="utf-8") as f:
        assert text == f.read()


def test_data_files_live_next_to_server_py(monkeypatch):
    # The isolated fixture points them at a temp folder; undo that to see the real defaults
    monkeypatch.undo()
    for path in (config.DATA_FILE, config.HASHBROWN_CONFIG):
        assert os.path.dirname(os.path.abspath(path)) == PROJECT
