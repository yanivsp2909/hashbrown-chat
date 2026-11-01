"""
👥 The Groups screen's rules (web/static/js/grouplogic.js), run in Node: which /commands each button sends,
mine-first sorting and search, the bank history lines, upgrade labels and the balance chart.
Skipped when Node isn't installed.
"""
import json
import shutil
import subprocess
import unittest

from harness import WEB

MODULE = (WEB / "static" / "js" / "grouplogic.js").as_uri()


def run(code):
    script = f"import * as G from {json.dumps(MODULE)};\n{code}"
    done = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=20)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


def out(expression):
    return run(f"console.log(JSON.stringify({expression}))")


@unittest.skipUnless(shutil.which("node"), "Node isn't installed")
class GroupLogicTestCase(unittest.TestCase):
    def test_buttons_send_the_existing_commands(self):
        group = '{key: "potatoes", name: "Potatoes"}'
        self.assertEqual(out(f"""[
            G.packetsFor("join", {group}, {{}}),
            G.packetsFor("open", {group}, {{}}),
            G.packetsFor("create", {{name: "Fries"}}, {{private: true}}),
            G.packetsFor("create", {{name: "Fries"}}, {{}}),
        ]"""), [[{"type": "line", "text": "/join Potatoes"}], [{"type": "line", "text": "/join Potatoes"}],
                [{"type": "line", "text": "/create Fries private"}], [{"type": "line", "text": "/create Fries"}]])

    def test_group_buttons_say_which_group_and_never_join_it_first(self):
        # 👥 the server runs a group command for the "group" field's group: you stay in the chat you're in
        group = '{key: "potatoes", name: "Potatoes"}'
        got = out(f"""[
            G.packetsFor("kick", {group}, {{target: "Ben"}}),
            G.packetsFor("approve", {group}, {{target: "Ben"}}),
            G.packetsFor("reject", {group}, {{target: "Ben"}}),
            G.packetsFor("mute", {group}, {{target: "Ben", value: 15}}),
            G.packetsFor("donate", {group}, {{value: 40}}),
            G.packetsFor("upgrade", {group}, {{value: "income"}}),
            G.packetsFor("topic", {group}, {{value: ""}}),
            G.packetsFor("topic", {group}, {{value: "Movie night"}}),
            G.packetsFor("persona", {group}, {{value: ""}}),
            G.packetsFor("leave", {group}, {{}}),
            G.packetsFor("disband", {group}, {{}}),
        ]""")
        self.assertEqual([p[0]["text"] for p in got],
                         ["/kick Ben", "/approve Ben", "/reject Ben", "/mute Ben 15", "/donate 40", "/upgrade income",
                          "/pin clear", "/pin Movie night", "/personality", "/leave", "/disband"])
        self.assertTrue(all(len(p) == 1 and p[0]["group"] == "potatoes" for p in got))

    def test_who_the_invite_picker_offers(self):
        # 📨 people online first, then names seen, never members or you, each once (case doesn't matter)
        self.assertEqual(out("""G.inviteCandidates(
            [{name: "Bobby"}, {name: "Alice"}, {name: "Cat"}, {}], ["Dan", "bobby", "Eve"], ["Alice", "Eve"], "Alice")"""),
            ["Bobby", "Cat", "Dan"])

    def test_an_unknown_action_sends_nothing(self):
        self.assertEqual(out('G.packetsFor("explode", {key: "potatoes", name: "Potatoes"}, {})'), [])

    def test_mine_first_then_the_rest_and_search(self):
        cards = ('[{key: "chess", name: "Chess", your_role: "none", topic: "knights"},'
                 ' {key: "potatoes", name: "Potatoes", your_role: "member", topic: "fries"},'
                 ' {key: "secret", name: "Secret", your_role: "requested"}]')
        self.assertEqual(out(f"""[G.split({cards}, ""), G.split({cards}, "FRI"), G.split({cards}, "kni")]"""), [
            {"mine": [{"key": "potatoes", "name": "Potatoes", "your_role": "member", "topic": "fries"}],
             "others": [{"key": "chess", "name": "Chess", "your_role": "none", "topic": "knights"},
                        {"key": "secret", "name": "Secret", "your_role": "requested"}]},
            {"mine": [{"key": "potatoes", "name": "Potatoes", "your_role": "member", "topic": "fries"}], "others": []},
            {"mine": [], "others": [{"key": "chess", "name": "Chess", "your_role": "none", "topic": "knights"}]},
        ])

    def test_bank_history_lines(self):
        self.assertEqual(out("""[
            G.historyLine({kind: "donate", who: "Ben", amount: 60, note: ""}),
            G.historyLine({kind: "upgrade", who: "Adi", amount: -150, note: "emoji"}),
            G.historyLine({kind: "war_won", who: "", amount: 300, note: "Blue"}),
            G.historyLine({kind: "war_lost", who: "", amount: -300, note: "Red"}),
            G.historyLine({kind: "hashbrown", who: "Adi", amount: -10, note: ""}),
            G.historyLine({kind: "refund", who: "Adi", amount: 10, note: ""}),
        ]"""), ["🤝 Ben donated", "⬆️ Adi bought emoji", "⚔️ Won the war against #Blue",
                "⚔️ Lost the war against #Red", "🥔 Hashbrown answered Adi", "↩️ Refund for Adi's question"])

    def test_upgrade_states_say_what_to_do(self):
        self.assertEqual(out("""[
            G.upgradeStatus({state: "owned"}), G.upgradeStatus({state: "can_buy"}),
            G.upgradeStatus({state: "locked", missing: 120}),
            G.balanceAfter({price: 150}, 420),
        ]"""), ["✅ Owned", "🟢 The bank can buy it now", "🔒 120 🪙 more needed", 270])

    def test_the_chart_needs_three_points_and_fits_the_box(self):
        result = out("""[G.chartPath([{time: 1, balance: 10}, {time: 2, balance: 30}], 100, 40),
                         G.chartPath([{time: 0, balance: 10}, {time: 5, balance: 30}, {time: 10, balance: 20}], 100, 40)]""")
        self.assertIsNone(result[0])
        chart = result[1]
        self.assertEqual((chart["min"], chart["max"], chart["first"], chart["last"]), (10, 30, 10, 20))
        self.assertTrue(chart["line"].startswith("M0,") and "L100," in chart["line"])
        self.assertTrue(chart["area"].endswith("Z"))

    def test_time_labels(self):
        self.assertEqual(out("""(() => {
            const now = new Date(2026, 9, 30, 22, 0).getTime() / 1000;
            return [G.timeLabel(new Date(2026, 9, 30, 9, 5).getTime() / 1000, now),
                    G.timeLabel(new Date(2026, 9, 28, 9, 5).getTime() / 1000, now)];
        })()"""), ["09:05", "28/10 09:05"])


    def test_a_members_admin_tools_are_one_tab_stop_with_arrow_keys_inside(self):
        # 5 tools (Kick, minutes, Mute, Ban, Promote): arrows move and wrap, Home/End jump, other keys are left alone
        self.assertEqual(out("""[["ArrowRight", 0], ["ArrowRight", 4], ["ArrowLeft", 0], ["ArrowLeft", 3],
            ["Home", 3], ["End", 1], ["ArrowDown", 2], ["Tab", 2], ["Enter", 1]].map(([k, i]) => G.toolbarIndex(k, i, 5))"""),
            [1, 0, 4, 2, 0, 4, None, None, None])

if __name__ == "__main__":
    unittest.main()
