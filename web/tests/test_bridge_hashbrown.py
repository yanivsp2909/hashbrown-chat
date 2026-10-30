"""
The temp_id / replaces fields of the "Hashbrown is thinking..." notice reach the website through the bridge.
Uses a fake local AI (tests/helpers.py FakeFoundry), never the real one. The browser side
(removing the card) is plain DOM code in web/static/js/chat.js and is not tested here.

Run:  python -m unittest discover -s web/tests -v      (from the project folder)
"""
import itertools
import sys
import unittest

from harness import ROOT, Browser, Stack, is_msg

sys.path.insert(0, str(ROOT / "tests"))
from helpers import FakeFoundry  # noqa: E402

PASSWORD = "pass1234"
names = (f"hbtester{i}" for i in itertools.count(1))


class TestThinkingNotice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.foundry = FakeFoundry()
        cls.stack = Stack(max_sessions=4, fake_ai_port=cls.foundry.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.stack.stop()
        cls.foundry.stop()

    def tab(self):
        browser = Browser(self.stack.web_port)
        self.addCleanup(browser.close)
        self.assertTrue(browser.auth(next(names), PASSWORD, "register")["ok"])
        browser.wait(is_msg(type_="history"), what="the lobby history")
        return browser

    def test_private_ask_answer_replaces_the_thinking_notice(self):
        tab = self.tab()
        tab.line("/ask hi")
        thinking = tab.wait(is_msg("🥔 Hashbrown is thinking"), what="the thinking notice")
        self.assertTrue(thinking["temp_id"].startswith("hb-"))
        answer = tab.wait(is_msg("🥔 Hashbrown (only you): ", "private"), what="the private answer")
        self.assertEqual(answer["replaces"], thinking["temp_id"])

    def test_public_answer_replaces_the_thinking_notice(self):
        tab = self.tab()
        tab.line("@hashbrown hi")
        thinking = tab.wait(is_msg("🥔 Hashbrown is thinking"), what="the thinking notice")
        answer = tab.wait(is_msg(type_="chat"), what="Hashbrown's chat message")
        # the first chat packet is the user's own line, so wait for Hashbrown's
        while answer.get("name") != "Hashbrown":
            answer = tab.wait(is_msg(type_="chat"), what="Hashbrown's chat message")
        self.assertEqual(answer["replaces"], thinking["temp_id"])


if __name__ == "__main__":
    unittest.main()
