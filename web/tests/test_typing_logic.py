"""
⌨️ "Noa is typing…" (web/static/js/typing.js), run in Node with a tiny fake page: only people typing in the
room you're looking at are shown, and switching rooms forgets the old room's typers.

Skipped when Node isn't installed.
"""
import json
import shutil
import subprocess
import unittest

from harness import WEB

MODULE = (WEB / "static" / "js" / "typing.js").as_uri()

PAGE = """
const line = { textContent: "", hidden: true };
globalThis.document = { getElementById: (id) => (id === "typing-line" ? line : { addEventListener() {} }) };
globalThis.sessionStorage = { getItem: () => null, setItem() {}, removeItem() {} };
globalThis.window = { addEventListener() {} };
const T = await import(%s);
""" % json.dumps(MODULE)


def run(code):
    done = subprocess.run(["node", "--input-type=module", "-e", PAGE + code], capture_output=True, text=True, timeout=20)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


@unittest.skipUnless(shutil.which("node"), "Node isn't installed")
class TypingLogicTestCase(unittest.TestCase):
    def test_someone_typing_in_another_room_isnt_shown(self):
        self.assertEqual(run("""
            T.onTyping({type: "typing", name: "Tal", room: "lobby"}, "potatoes");
            const other = [line.textContent, line.hidden];
            T.onTyping({type: "typing", name: "Ben", room: "potatoes"}, "potatoes");
            T.onTyping({type: "typing", name: "Old"}, "potatoes");   // no room field (an older server): shown
            console.log(JSON.stringify([other, line.textContent]));"""),
            [["", True], "Ben and Old are typing…"])

    def test_switching_rooms_forgets_the_old_rooms_typers(self):
        self.assertEqual(run("""
            T.onTyping({type: "typing", name: "Tal", room: "lobby"}, "lobby");
            const before = line.textContent;
            T.forgetTypers();
            console.log(JSON.stringify([before, line.textContent, line.hidden]));"""),
            ["Tal is typing…", "", True])
