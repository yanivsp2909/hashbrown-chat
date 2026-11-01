"""
🤝 The friends list's rules (web/static/js/friendlogic.js), run in Node: what a server "friends" packet
becomes, the line under each friend's name, and which group the "invite to my group" button uses.

Skipped when Node isn't installed.
"""
import json
import shutil
import subprocess
import unittest

from harness import WEB

MODULE = (WEB / "static" / "js" / "friendlogic.js").as_uri()


def run(code):
    script = f"import * as F from {json.dumps(MODULE)};\n{code}"
    done = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=20)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


@unittest.skipUnless(shutil.which("node"), "Node isn't installed")
class FriendLogicTestCase(unittest.TestCase):
    def test_a_packet_becomes_a_clean_list(self):
        got = run("""console.log(JSON.stringify(F.readFriends({type: "friends",
            friends: [{name: "Ben", online: true, status: "away", room: "#Potatoes", playing: true}, {name: 5}, null,
                      {name: "Cat", online: false, room: "", playing: false}],
            requests: ["Dan", 7], sent: ["Eve"], groups: [{key: "potatoes", name: "Potatoes"}, {key: 1}]})))""")
        self.assertEqual(got, {
            "friends": [{"name": "Ben", "online": True, "status": "away", "room": "#Potatoes", "playing": True},
                        {"name": "Cat", "online": False, "status": "online", "room": "", "playing": False}],
            "requests": ["Dan"], "sent": ["Eve"], "groups": [{"key": "potatoes", "name": "Potatoes"}]})

    def test_junk_is_an_empty_list(self):
        self.assertEqual(run('console.log(JSON.stringify(F.readFriends({type: "friends", friends: "x"})))'),
                         {"friends": [], "requests": [], "sent": [], "groups": []})

    def test_what_a_friend_is_doing(self):
        got = run("""console.log(JSON.stringify([
            F.doing({online: true, status: "online", room: "#Potatoes", playing: true}),
            F.doing({online: true, status: "busy", room: "🏠 Lobby", playing: false}),
            F.doing({online: true, status: "away", room: "🔒 a private group", playing: false}),
            F.doing({online: false, status: "online", room: "", playing: false})]))""")
        self.assertEqual(got, ["🎮 in a game · #Potatoes", "⛔ busy · 🏠 Lobby", "🌙 away · 🔒 a private group", "offline"])

    def test_counting_who_is_online(self):
        self.assertEqual(run('console.log(JSON.stringify(F.onlineCount([{online: true}, {online: false}, {online: true}])))'), 2)

    def test_which_group_the_invite_button_uses(self):
        got = run("""const g = [{key: "fries", name: "Fries"}, {key: "potatoes", name: "Potatoes"}];
            console.log(JSON.stringify([F.inviteChoices(g, "potatoes"), F.inviteChoices(g, "lobby"), F.inviteChoices([], "lobby")]));""")
        self.assertEqual(got, [[{"key": "potatoes", "name": "Potatoes"}, {"key": "fries", "name": "Fries"}],
                               [{"key": "fries", "name": "Fries"}, {"key": "potatoes", "name": "Potatoes"}], []])


if __name__ == "__main__":
    unittest.main()
