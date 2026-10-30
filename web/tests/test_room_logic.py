"""
💬 The chat switcher's rules (web/static/js/roomlogic.js), run in Node: every chat (the Lobby and each
group) is its own conversation, with its own message list, preview line and unread count.

Skipped when Node isn't installed.
"""
import json
import shutil
import subprocess
import unittest

from harness import WEB

MODULE = (WEB / "static" / "js" / "roomlogic.js").as_uri()


def run(code):
    """Run `code` as an ES module that has the roomlogic.js exports as `R`; returns what it prints as JSON."""
    script = f"import * as R from {json.dumps(MODULE)};\n{code}"
    done = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=20)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


@unittest.skipUnless(shutil.which("node"), "Node isn't installed")
class RoomLogicTestCase(unittest.TestCase):
    def test_a_history_after_login_means_a_new_room_so_the_list_starts_empty(self):
        self.assertEqual(run("""console.log(JSON.stringify([
            R.startsNewList({type: "history", key: "potatoes"}, "lobby"),
            R.startsNewList({type: "history", key: "lobby"}, "potatoes"),
            R.startsNewList({type: "history", key: "lobby"}, ""),
            R.startsNewList({type: "chat", room: "lobby"}, "potatoes"),
        ]))"""), [True, True, False, False])   # the first history (at login) keeps the welcome lines

    def test_messages_from_another_room_belong_there(self):
        self.assertEqual(run("""console.log(JSON.stringify([
            R.roomOf({type: "chat", room: "potatoes"}, "lobby"),
            R.roomOf({type: "chat", room: "lobby"}, "lobby"),
            R.roomOf({type: "msg", text: "hi"}, "lobby"),
            R.roomOf({type: "history", room: "#Potatoes", key: "potatoes"}, "lobby"),
        ]))"""), ["potatoes", "lobby", "lobby", "potatoes"])

    def test_each_room_gets_its_own_preview(self):
        self.assertEqual(run("""
            let previews = {};
            previews = R.withPreview(previews, {type: "chat", room: "lobby", name: "Adi", text: "hello lobby"}, "lobby");
            previews = R.withPreview(previews, {type: "chat", room: "potatoes", name: "Adi", text: "hello potatoes"}, "lobby");
            previews = R.withPreview(previews, {type: "history", key: "potatoes", room: "#Potatoes",
                messages: [{name: "Ben", text: "first"}, {name: "Adi", text: "last one"}]}, "lobby");
            console.log(JSON.stringify(previews))"""),
            {"lobby": "Adi: hello lobby", "potatoes": "Adi: last one"})


if __name__ == "__main__":
    unittest.main()
