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
MENTIONS = (WEB / "static" / "js" / "mentions.js").as_uri()


def run(code):
    """Run `code` as an ES module with roomlogic.js as `R` and mentions.js as `M`; returns what it prints as JSON."""
    script = f"import * as R from {json.dumps(MODULE)};\nimport * as M from {json.dumps(MENTIONS)};\n{code}"
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


@unittest.skipUnless(shutil.which("node"), "Node isn't installed")
class MentionsTestCase(unittest.TestCase):
    """@ autocomplete: typing @ suggests @hashbrown and the people in this chat."""

    def test_the_word_after_an_at_sign_is_found_at_the_caret(self):
        self.assertEqual(run("""console.log(JSON.stringify([
            M.mentionAt("hey @no", 7), M.mentionAt("@", 1), M.mentionAt("mail me@home", 12),
            M.mentionAt("hey @noa and", 12), M.mentionAt("hey @noa and", 8),
        ]))"""), [{"start": 4, "end": 7, "word": "no"}, {"start": 0, "end": 1, "word": ""}, None, None,
                  {"start": 4, "end": 8, "word": "noa"}])

    def test_hashbrown_and_the_people_in_this_room_but_not_you(self):
        self.assertEqual(run("""console.log(JSON.stringify(M.mentionNames({room: "#Potatoes", nick: "Adi", knownNames: [],
            online: [{name: "Adi", room: "#Potatoes"}, {name: "Noa", room: "#Potatoes"}, {name: "Ben", room: "🏠 Lobby"}]})))"""),
            ["hashbrown", "Noa"])

    def test_before_the_online_list_arrives_everyone_seen_counts(self):
        self.assertEqual(run("""console.log(JSON.stringify(M.matchingNames(
            M.mentionNames({room: "x", nick: "Adi", online: null, knownNames: ["Noa", "Nir", "Adi"]}), "N")))"""),
            ["Noa", "Nir"])


if __name__ == "__main__":
    unittest.main()
