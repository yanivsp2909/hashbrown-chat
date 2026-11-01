"""
🏢 The Ventures screen's rules (web/static/js/ventureslogic.js), run in Node: money and percents, the command each
button sends, the name rule, the chart and pie shapes, the countdown, hiding the screen's commands from /help, and
reading broken packets safely. Skipped when Node isn't installed.
"""
import json
import shutil
import subprocess
import unittest

from harness import WEB

MODULE = (WEB / "static" / "js" / "ventureslogic.js").as_uri()


def run(expression):
    script = f"import * as V from {json.dumps(MODULE)};\nconsole.log(JSON.stringify({expression}));"
    done = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=20)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


@unittest.skipUnless(shutil.which("node"), "Node isn't installed")
class VenturesLogicTestCase(unittest.TestCase):
    def test_money_and_percents_read_like_the_server(self):
        self.assertEqual(run("[V.money(950), V.money(12340), V.money(999960), V.money(4.5e6), V.money(-5000), V.money(1.2e9)]"),
                         ["$950", "$12.3K", "$1M", "$4.5M", "-$5K", "$1.2B"])
        self.assertEqual(run("[V.percent(1250), V.percent(10000), V.percent(5)]"), ["12.5%", "100%", "0.05%"])
        self.assertEqual(run("[V.plural(1, 'day'), V.plural(3, 'day'), V.runwayText(null), V.runwayText(0)]"),
                         ["1 day", "3 days", "∞ profitable", "out today"])

    def test_buttons_send_the_same_commands_a_player_would_type(self):
        self.assertEqual(run("""[V.foundLine(' Spudly ', 'saas'), V.actionLine('build'), V.actionLine('hire', 'engineer'),
            V.actionLine('layoff', 'sales', 0), V.inviteLine('Ben', 'cto', 10), V.inviteLine('Ben', 'engineer', 0),
            V.angelLine(true, 'Cat'), V.angelLine(false, 'Cat'), V.investLine('Spudly', 150.7),
            V.offerLine('accept', 'c1-idea-5'), V.pitchLine('We  build\\npotatoes ')]"""),
                         ["/company found Spudly saas", "/company build", "/company hire engineer",
                          "/company layoff sales 1", "/company invite Ben cto 10", "/company invite Ben engineer",
                          "/company angel accept Cat", "/company angel decline Cat", "/invest Spudly 150",
                          "/offer accept c1-idea-5", "/pitch We build potatoes"])

    def test_counters_and_percents_typed_in_boxes(self):
        self.assertEqual(run("[V.counterLine('15m'), V.counterLine('$2,500,000'), V.counterLine('lots'), V.counterLine('-5M')]"),
                         ["/offer counter 15M", "/offer counter 2500000", None, None])
        self.assertEqual(run("[V.readPercent('12.5'), V.readPercent('10%'), V.readPercent('150'), V.readPercent('x')]"),
                         [12.5, 10, None, None])

    def test_the_name_rule_matches_the_server(self):
        self.assertEqual(run("[V.nameProblem('Spudly'), V.nameProblem('תפוח'), V.nameProblem('ab'), V.nameProblem('Spud ly'), V.nameProblem('Lobby'), V.nameProblem('Aתפ')].map(Boolean)"),
                         [False, False, True, True, True, True])

    def test_chart_and_pie_shapes(self):
        shape = run("V.chart([1, 3, 2])")
        self.assertTrue(shape["path"].startswith("M") and shape["min"] == 1 and shape["max"] == 3 and shape["last"] == 2)
        self.assertIsNone(run("V.chart([5])"))
        slices = run("V.pie([{name: 'Adi', bp: 7500}, {name: 'Maya', bp: 2500}, {name: 'Zero', bp: 0}])")
        self.assertEqual([s["name"] for s in slices], ["Adi", "Maya"])
        self.assertIn(" 1 1 ", slices[0]["path"])   # three quarters: the long way round
        self.assertIn("A46,46", run("V.pie([{name: 'All', bp: 10000}])")[0]["path"])

    def test_the_countdown(self):
        self.assertEqual(run("[V.countdown(3600 * 3 + 720, 0), V.countdown(300, 0), V.countdown(10, 0), V.countdown(7200, 0)]"),
                         ["in 3 h 12 min", "in 5 min", "any minute now", "in 2 h"])

    def test_the_help_hides_the_screens_commands(self):
        text = "📖 COMMANDS\\n\\n🏢 Ventures\\n  /company x   y\\n  /pitch   z\\n\\n🎮 Games\\n  /games   list"
        got = run(f'V.hideVenturesHelp("{text}")')
        self.assertNotIn("/company", got)
        self.assertNotIn("/pitch", got)
        self.assertIn("open 🏢 Ventures in the menu", got)
        self.assertIn("/games", got)
        names = run("V.withoutScreenCommands([{name: '/company'}, {name: '/invest'}, {name: '/games'}, {name: '/offer'}]).map(c => c.name)")
        self.assertEqual(names, ["/games"])

    def test_broken_packets_draw_as_empty(self):
        home = run("V.readHome({board: 'x', investments: null, mine: {name: 5}})")
        self.assertEqual((home["board"], home["mine"], home["investments"]), ([], None, {"held": [], "waiting": []}))
        self.assertIsNone(run("V.readCompany({company: {name: 'no id'}})"))
        self.assertEqual(run("V.readCompany({company: {id: 'c1', team: 'x'}}).team"), [])
