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
            G.commandsFor("join", {group}, {{currentRoom: "lobby"}}),
            G.commandsFor("approve", {group}, {{currentRoom: "lobby", target: "Ben"}}),
            G.commandsFor("reject", {group}, {{currentRoom: "lobby", target: "Ben"}}),
            G.commandsFor("create", {{name: "Fries"}}, {{private: true}}),
            G.commandsFor("create", {{name: "Fries"}}, {{}}),
        ]"""), [["/join Potatoes"], ["/approve Ben Potatoes"], ["/reject Ben Potatoes"],
                ["/create Fries private"], ["/create Fries"]])

    def test_commands_for_the_room_youre_in_join_it_first_only_when_needed(self):
        group = '{key: "potatoes", name: "Potatoes"}'
        self.assertEqual(out(f"""[
            G.commandsFor("kick", {group}, {{currentRoom: "lobby", target: "Ben"}}),
            G.commandsFor("kick", {group}, {{currentRoom: "potatoes", target: "Ben"}}),
            G.commandsFor("mute", {group}, {{currentRoom: "potatoes", target: "Ben", value: 15}}),
            G.commandsFor("donate", {group}, {{currentRoom: "potatoes", value: 40}}),
            G.commandsFor("upgrade", {group}, {{currentRoom: "potatoes", value: "income"}}),
            G.commandsFor("topic", {group}, {{currentRoom: "potatoes", value: ""}}),
            G.commandsFor("topic", {group}, {{currentRoom: "potatoes", value: "Movie night"}}),
            G.commandsFor("persona", {group}, {{currentRoom: "potatoes", value: ""}}),
            G.commandsFor("leave", {group}, {{currentRoom: "lobby"}}),
            G.commandsFor("disband", {group}, {{currentRoom: "potatoes"}}),
        ]"""), [["/join Potatoes", "/kick Ben"], ["/kick Ben"], ["/mute Ben 15"], ["/donate 40"],
                ["/upgrade income"], ["/pin clear"], ["/pin Movie night"], ["/personality"],
                ["/join Potatoes", "/leave"], ["/disband"]])

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


if __name__ == "__main__":
    unittest.main()
