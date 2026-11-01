"""
🔬 Packet X-ray's memory (web/static/js/xraylog.js), run in Node: it keeps the newest 500 entries from page load,
filters them by packet type (also inside raw TCP chunks, which can hold several packets or half of one),
and clears.

Skipped when Node isn't installed.
"""
import json
import shutil
import subprocess
import unittest

from harness import WEB

MODULE = (WEB / "static" / "js" / "xraylog.js").as_uri()


def run(code):
    script = f"import * as X from {json.dumps(MODULE)};\n{code}"
    done = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=20)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


@unittest.skipUnless(shutil.which("node"), "Node isn't installed")
class XrayLogTestCase(unittest.TestCase):
    def test_it_keeps_the_newest_500_and_says_which_one_fell_out(self):
        self.assertEqual(run("""
            const log = X.makeLog();
            let dropped = null;
            for (let i = 0; i < 503; i++) dropped = log.add({ n: i, types: ["chat"] });
            const all = log.list();
            console.log(JSON.stringify([X.XRAY_KEEP, all.length, all[0].n, all.at(-1).n, dropped.n]));"""),
            [500, 500, 3, 502, 2])

    def test_nothing_falls_out_before_the_log_is_full(self):
        self.assertEqual(run("""
            const log = X.makeLog(3);
            console.log(JSON.stringify([log.add({ types: [] }), log.add({ types: [] }), log.list().length]));"""),
            [None, None, 2])

    def test_a_filter_shows_only_that_packet_type(self):
        self.assertEqual(run("""
            const log = X.makeLog();
            log.add({ n: 1, types: ["chat"] });
            log.add({ n: 2, types: ["board"] });
            log.add({ n: 3, types: ["chat", "typing"] });
            console.log(JSON.stringify([log.list("chat").map((e) => e.n), log.list("").length, log.types(),
                                        X.matches({ types: ["board"] }, "chat"), X.matches({ types: [] }, "")]));"""),
            [[1, 3], 3, ["board", "chat", "typing"], False, True])

    def test_clear_empties_it(self):
        self.assertEqual(run("""
            const log = X.makeLog();
            log.add({ types: ["chat"] });
            log.empty();
            console.log(JSON.stringify([log.list(), log.types()]));"""),
            [[], []])

    def test_the_packet_types_inside_a_tcp_chunk(self):
        # two whole packets, then the start of a third (cut in the middle: TCP is a stream)
        chunk = '{"type":"chat","text":"hi"}\n{"text":"x","type":"typing"}\n{"type":"board","state":{"ty'
        self.assertEqual(run(f"""
            console.log(JSON.stringify([X.chunkTypes({json.dumps(chunk)}), X.chunkTypes(""),
                                        X.chunkTypes('{{"type":"msg","data":{{"type":"inner"}}}}\\n')]));"""),
            [["chat", "typing", "board"], [], ["msg"]])

    def test_passwords_and_reconnect_tokens_are_never_kept(self):
        got = run("""
            const login = {type: "auth", action: "login", username: "Noa", password: "hunter22", features: []};
            const result = {type: "auth_result", ok: true, text: "Welcome", resume_token: "SECRETTOKEN"};
            const resume = {type: "auth", action: "resume", username: "Noa", token: "SECRETTOKEN2"};
            const change = {type: "change_password", old: "hunter22", new: "hunter33"};
            const chat = {type: "chat", text: "hi"};
            console.log(JSON.stringify([login, result, resume, change, chat].map((p) => X.hideSecrets(p, JSON.stringify(p)))));""")
        joined = " ".join(got)
        for secret in ("hunter22", "hunter33", "SECRETTOKEN"):
            self.assertNotIn(secret, joined)
        self.assertIn('"resume_token":"•••"', got[1])
        self.assertEqual(got[4], '{"type":"chat","text":"hi"}')   # everything else is shown exactly as sent


if __name__ == "__main__":
    unittest.main()
