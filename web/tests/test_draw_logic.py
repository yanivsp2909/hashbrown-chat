"""
🎨 The drawer's outbox (web/static/js/drawlogic.js), run in Node with a fake clock: points are batched into at
most one stroke packet every 100 ms, nothing is lost, and the pieces of a long line join up.

Skipped when Node isn't installed.
"""
import json
import shutil
import subprocess
import unittest

from harness import WEB

MODULE = (WEB / "static" / "js" / "drawlogic.js").as_uri()

# A fake clock: later() queues timers, run(ms) moves time forward and fires what's due, in order.
CLOCK = """
let t = 0; let timers = []; const sent = [];
const now = () => t;
const later = (fn, ms) => { timers.push({at: t + ms, fn}); };
function run(ms) {
  const end = t + ms;
  for (;;) {
    timers.sort((a, b) => a.at - b.at);
    if (!timers.length || timers[0].at > end) break;
    const next = timers.shift(); t = next.at; next.fn();
  }
  t = end;
}
const B = D.makeBatcher((p) => sent.push({...p, t}), now, later);
"""


def run(code):
    script = f"import * as D from {json.dumps(MODULE)};\n{CLOCK}\n{code}"
    done = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=20)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


@unittest.skipUnless(shutil.which("node"), "Node isn't installed")
class DrawLogicTestCase(unittest.TestCase):
    def test_a_fast_ten_second_drawing_goes_out_whole_at_most_ten_packets_a_second(self):
        result = run("""
            // 10 seconds at 60 points a second, a new line every second
            let n = 0;
            for (let line = 0; line < 10; line++) {
              B.start([n, line], 1, 2); n++; run(16);
              for (let i = 0; i < 59; i++) { B.add([n, line]); n++; run(16); }
              B.end(); run(40);
            }
            run(5000);
            const gaps = sent.slice(1).map((p, i) => p.t - sent[i].t);
            const xs = [...new Set(sent.flatMap((p) => p.points.map(([x]) => x)))];
            console.log(JSON.stringify({count: sent.length, minGap: Math.min(...gaps), xs: xs.length, total: n,
              sorted: xs.every((x, i) => !i || x > xs[i - 1])}));""")
        self.assertGreaterEqual(result["minGap"], 100)              # never faster than one every 100 ms
        self.assertLessEqual(result["count"], 10 * 11)             # about 10 a second, not one per mouse move
        self.assertEqual((result["xs"], result["sorted"]), (result["total"], True))   # every point, in order

    def test_the_pieces_of_a_long_line_join_up_and_each_line_is_its_own_packet(self):
        result = run("""
            B.start([0, 0], 3, 1); for (let i = 1; i < 150; i++) B.add([i, 0]);
            B.end(); B.start([500, 500], 5, 3); B.add([501, 501]); B.end();
            run(2000);
            console.log(JSON.stringify(sent.map((p) => [p.points[0][0], p.points[p.points.length - 1][0], p.points.length, p.color])));""")
        self.assertEqual(result, [[0, 59, 60, 3], [59, 118, 60, 3], [118, 149, 32, 3], [500, 501, 2, 5]])

    def test_a_single_tap_is_a_dot_and_dropping_forgets_everything(self):
        result = run("""
            B.start([7, 7], 0, 2); B.end(); run(200);
            B.start([1, 1], 0, 2); B.add([2, 2]); B.drop(); run(500);
            console.log(JSON.stringify(sent.map((p) => p.points)));""")
        self.assertEqual(result, [[[7, 7]]])
