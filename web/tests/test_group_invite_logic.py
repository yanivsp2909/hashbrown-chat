"""
📨 Group invite tickets (web/static/js/groupinvites.js), run in Node: what a server "group_invite" field becomes,
one ticket per group, gone when it's answered or ends, and the "time left" words.

Skipped when Node isn't installed.
"""
import json
import shutil
import subprocess
import unittest

from harness import WEB

MODULE = (WEB / "static" / "js" / "groupinvites.js").as_uri()


def run(code):
    script = f"import * as I from {json.dumps(MODULE)};\n{code}"
    done = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=20)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


@unittest.skipUnless(shutil.which("node"), "Node isn't installed")
class GroupInviteLogicTestCase(unittest.TestCase):
    def test_a_good_field_becomes_an_invite_and_junk_is_ignored(self):
        self.assertEqual(run("""
            const good = {group: "potatoes", name: "Potatoes", from: "Adi", expires: 2000};
            console.log(JSON.stringify([I.readInvite(good), I.readInvite(null), I.readInvite({group: "x"}),
              I.readInvite({...good, expires: "soon"}), I.readInvite({...good, name: 5}), I.readInvite([1])]));"""),
            [{"group": "potatoes", "name": "Potatoes", "from": "Adi", "expires": 2000}, None, None, None, None, None])

    def test_one_ticket_per_group_and_answered_ones_go(self):
        self.assertEqual(run("""
            const a = {group: "potatoes", name: "Potatoes", from: "Adi", expires: 2000};
            const b = {group: "fries", name: "Fries", from: "Ben", expires: 3000};
            let list = I.withInvite([], a);
            list = I.withInvite(list, b);
            list = I.withInvite(list, {...a, from: "Cat", expires: 5000});   // a new invite to the same group
            const after = I.withoutInvite(list, "fries");
            console.log(JSON.stringify([list.map((i) => i.from), after.map((i) => i.group)]));"""),
            [["Ben", "Cat"], ["potatoes"]])

    def test_ended_invites_are_left_out(self):
        self.assertEqual(run("""
            const list = [{group: "a", expires: 100}, {group: "b", expires: 300}];
            console.log(JSON.stringify(I.stillOpen(list, 200).map((i) => i.group)));"""), ["b"])

    def test_time_left_in_words(self):
        self.assertEqual(run("""
            const now = 1000;
            console.log(JSON.stringify([I.timeLeft(now + 24 * 3600, now), I.timeLeft(now + 90 * 60, now),
                                        I.timeLeft(now + 45 * 60, now), I.timeLeft(now + 20, now), I.timeLeft(now - 5, now)]));"""),
            ["24 h left", "2 h left", "45 min left", "1 min left", "ended"])

    def test_the_answers_are_existing_commands(self):
        self.assertEqual(run("""
            const invite = {group: "potatoes", name: "Potatoes", from: "Adi", expires: 2000};
            console.log(JSON.stringify([I.answerLine(invite, "accept"), I.answerLine(invite, "decline")]));"""),
            ["/join Potatoes", "/invites decline Potatoes"])


if __name__ == "__main__":
    unittest.main()
