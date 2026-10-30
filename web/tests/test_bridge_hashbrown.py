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

    def tab(self, features=None):
        browser = Browser(self.stack.web_port)
        self.addCleanup(browser.close)
        self.assertTrue(browser.auth(next(names), PASSWORD, "register", features)["ok"])
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

    # ----- streaming: a tab that logged in with features=["stream"] gets the live pieces

    def set_pieces(self, pieces):
        self.foundry.pieces = pieces
        self.addCleanup(setattr, self.foundry, "pieces", None)

    def test_stream_packets_reach_the_browser_then_the_final_message(self):
        self.set_pieces(["Hello ", "from ", "the stream"])
        tab = self.tab(["stream"])
        tab.line("@hashbrown hi")
        thinking = tab.wait(is_msg("🥔 Hashbrown is thinking"), what="the thinking notice")
        first = tab.wait(is_msg(type_="stream"), what="the first stream packet")
        self.assertEqual(first["replaces"], thinking["temp_id"])
        self.assertEqual(first["stream_id"], thinking["temp_id"])
        final = tab.wait(lambda e: e["data"].get("type") == "chat" and e["data"].get("name") == "Hashbrown",
                         what="Hashbrown's final message")
        self.assertEqual(final["stream_id"], thinking["temp_id"])
        self.assertTrue(final["done"])
        self.assertEqual(final["text"], "Hello from the stream")
        pieces = [e["data"]["append"] for e in tab.stream.seen if e["data"].get("type") == "stream"]
        self.assertEqual("".join(pieces), "Hello from the stream")

    def test_a_tab_without_features_gets_no_stream_packets(self):
        self.set_pieces(["Hello ", "from ", "the stream"])
        tab = self.tab()
        tab.line("@hashbrown hi")
        final = tab.wait(lambda e: e["data"].get("name") == "Hashbrown", what="Hashbrown's message")
        self.assertEqual(final["text"], "Hello from the stream")
        self.assertFalse([e for e in tab.stream.seen if e["data"].get("type") == "stream"])

    def test_bad_features_are_refused_by_the_bridge(self):
        browser = Browser(self.stack.web_port)
        self.addCleanup(browser.close)
        for bad in ("stream", ["x" * 21], ["a"] * 9, [1]):
            status, _ = browser.send({"type": "auth", "action": "login", "username": "nobody1",
                                      "password": PASSWORD, "features": bad})
            self.assertEqual(status, 400, bad)


if __name__ == "__main__":
    unittest.main()
