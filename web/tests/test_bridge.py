"""
Smoke test for the website bridge, against a real copy of the chat server.

Run:  python -m unittest discover -s web/tests -v      (from the project folder)
"""
import base64
import itertools
import posixpath
import re
import socket
import time
import unittest

from harness import ROOT, WEB, Browser, Stack, Stream, is_msg, request

stack = None
names = (f"tester{i}" for i in itertools.count(1))
real_data = ROOT / "chat_data.json"
real_data_mtime = None
PASSWORD = "pass1234"


def setUpModule():
    global stack, real_data_mtime
    real_data_mtime = real_data.stat().st_mtime if real_data.exists() else None
    stack = Stack(max_sessions=4)


def tearDownModule():
    stack.stop()


def is_board(game):
    return lambda e: e["data"].get("kind") == "board" and (e["data"].get("state") or {}).get("game") == game


class BridgeTestCase(unittest.TestCase):
    def tab(self):
        browser = Browser(stack.web_port)
        self.addCleanup(browser.close)
        return browser

    def user(self, action="register"):
        """A new tab logged in as a brand new account. Returns (browser, nick)."""
        browser, name = self.tab(), next(names)
        result = browser.auth(name, PASSWORD, action)
        self.assertTrue(result["ok"], result)
        browser.wait(is_msg(type_="history"), what="the lobby history")
        return browser, name


def play_ttt(test, a, a_name, b, b_name, cells):
    """A challenges B, B accepts, then both alternate on `cells`, starting with whoever goes first."""
    a.line(f"/challenge {b_name} ttt")
    invite = b.wait(is_msg("⚔️", "event"), what="the challenge")
    test.assertIn(f"/accept {a_name}", invite["text"])
    b.line(f"/accept {a_name}")
    first = a.wait(is_board("ttt"), what="the first ttt board")["state"]
    order = [a, b] if first["your_turn"] else [b, a]
    for i, cell in enumerate(cells):
        mover = order[i % 2]
        mover.line(str(cell))
        board = mover.wait(lambda e: is_board("ttt")(e) and
                           sum(1 for c in e["data"]["state"]["cells"] if c) == i + 1,
                           what=f"the board after move {i + 1}")
    return order, board


class TestLoginAndChat(BridgeTestCase):
    def test_register_login_and_wrong_password(self):
        a, name = self.user()
        a.close()
        time.sleep(0.3)  # let the server notice the disconnect
        b = self.tab()
        self.assertFalse(b.auth(name, "wrong-password")["ok"])
        result = b.auth(name, PASSWORD)
        self.assertTrue(result["ok"], result)
        self.assertIn(name, result["text"])

    def test_chat_reaches_everyone(self):
        a, a_name = self.user()
        b, _ = self.user()
        a.line("hello from the web 👋")
        msg = b.wait(is_msg(type_="chat"), what="A's chat line")
        self.assertEqual(msg["name"], a_name)
        self.assertEqual(msg["text"], "hello from the web 👋")

    def test_command_reply(self):
        a, _ = self.user()
        a.line("/balance")
        self.assertIn("tokens", a.wait(is_msg("🪙", "money"), what="the /balance reply")["text"])


class TestGamesAndFiles(BridgeTestCase):
    def test_ttt_game_between_two_sessions(self):
        a, a_name = self.user()
        b, b_name = self.user()
        order, board = play_ttt(self, a, a_name, b, b_name, [1, 4, 2, 5, 3])
        self.assertTrue(board["state"]["finished"])
        winner, loser = order
        self.assertTrue(winner.wait(is_msg("🏆 YOU WON!"), what="the win message")["text"])
        self.assertTrue(loser.wait(is_msg("💀 You lost."), what="the loss message")["text"])

    def test_wordle(self):
        a, _ = self.user()
        a.line("/wordle")
        start = a.wait(is_board("wordle"), what="the wordle board")["state"]
        self.assertEqual((start["max_tries"], start["guesses"]), (6, []))
        a.line("/g crane")
        state = a.wait(lambda e: is_board("wordle")(e) and e["data"]["state"]["guesses"], what="a guess")["state"]
        self.assertEqual(state["guesses"][0]["word"], "crane")
        self.assertTrue(set(state["guesses"][0]["colors"]) <= {"green", "yellow", "gray"})

    def test_file_transfer(self):
        a, _ = self.user()
        b, b_name = self.user()
        payload = bytes(range(256)) * 40
        a.send({"type": "file", "to": b_name, "filename": "../../evil.txt",
                "data": base64.b64encode(payload).decode()})
        got = b.wait(lambda e: e["data"].get("type") == "file", what="the file")
        self.assertEqual(got["filename"], "evil.txt")
        self.assertEqual(base64.b64decode(got["data"]), payload)

    def test_a_tab_that_says_offers_is_asked_first(self):
        a, a_name = self.user()
        b = self.tab()
        b_name = next(names)
        self.assertTrue(b.auth(b_name, PASSWORD, "register", ["offers"])["ok"])
        a.send({"type": "file", "to": b_name, "filename": "x.txt", "data": base64.b64encode(b"hi").decode()})
        offer = b.wait(lambda e: "offer" in e["data"], what="the file offer")["offer"]
        self.assertEqual((offer["from"], offer["filename"]), (a_name, "x.txt"))
        self.assertFalse([e for e in b.stream.seen if e["data"].get("type") == "file"])
        b.line(f"/accept file {offer['id']}")
        self.assertEqual(b.wait(lambda e: e["data"].get("type") == "file", what="the file")["data"], "aGk=")


class TestServerStrings(BridgeTestCase):
    """patterns.js depends on exact server wording. If the server changes, this fails loudly."""

    def test_patterns_still_match_the_real_server(self):
        source = (WEB / "static" / "js" / "patterns.js").read_text(encoding="utf-8")
        patterns = dict(re.findall(r"(\w+): P\(String\.raw`([^`]*)`\)", source))
        self.assertGreater(len(patterns), 5, "couldn't read the patterns out of patterns.js")
        samples = self.collect_samples()
        problems = []
        for name, regex in patterns.items():
            if name not in samples:
                problems.append(f"{name}: the test has no real server sample for this pattern; add one")
            for text in samples.get(name, []):
                if not re.search(regex, text):
                    problems.append(f"{name}: /{regex}/ no longer matches the server's text {text!r}")
        hashbrown = re.search(r'HASHBROWN = Object\.freeze\(\{ name: "(\w+)", badge: "([^"]+)" \}\)', source)
        if not hashbrown or f'chat_message("{hashbrown[1]}", "{hashbrown[2]}"' not in stack.source_text():
            problems.append("HASHBROWN: the server no longer sends Hashbrown's answers as "
                            "chat_message(\"Hashbrown\", \"🥔\", ...)")
        self.assertFalse(problems, "\n\nServer text changed; update web/static/js/patterns.js:\n  "
                         + "\n  ".join(problems))

    def collect_samples(self):
        samples = {}
        a, b = self.tab(), self.tab()
        a_name, b_name = next(names), next(names)
        samples["welcome"] = [a.auth(a_name, PASSWORD, "register")["text"]]
        a.close()
        time.sleep(0.3)
        a = self.tab()
        samples["welcome"].append(a.auth(a_name, PASSWORD)["text"])
        b.auth(b_name, PASSWORD, "register")
        old_b, b = b, self.tab()  # logging in again from a new tab takes over the old one
        self.assertTrue(b.auth(b_name, PASSWORD)["ok"])
        old_b.wait(is_msg("🔁", "error"), what="the 'logged in from another window' notice")

        a.line("/help")
        help_text = a.wait(is_msg(kind="help"), what="the /help reply")["text"]
        usage_lines = [line for line in help_text.split("\n") if line.startswith("  /")]
        self.assertGreater(len(usage_lines), 20, "the /help reply has fewer command lines than expected")
        samples["helpLine"] = usage_lines

        a.line("/users")
        samples["onlineList"] = [a.wait(is_msg("🟢"), what="the /users reply")["text"]]
        a.line("/balance")
        samples["balance"] = [a.wait(is_msg("🪙", "money"), what="the /balance reply")["text"]]
        samples["balance"] += [m["data"]["text"] for m in a.stream.seen if is_msg("🪙 You have", "money")(m)]
        a.line(f"/send {b_name} psst")
        samples["privateMsg"] = [b.wait(is_msg("💌", "private"), what="the private message")["text"]]
        samples["presence"] = [m["data"]["text"] for m in a.stream.seen if is_msg("👋")(m)]

        new_nick = a_name + "x"
        a.line(f"/nick {new_nick}")
        samples["renamed"] = [a.wait(is_msg("✏️"), what="the /nick notice")["text"]]
        a_name = new_nick

        order, _ = play_ttt(self, a, a_name, b, b_name, [1, 4, 2, 5, 3])
        samples["invite"] = [m["data"]["text"] for m in b.stream.seen if is_msg("⚔️", "event")(m)]
        samples["won"] = [order[0].wait(is_msg(kind="money"), what="the win message")["text"]]
        samples["lost"] = [order[1].wait(is_msg(kind="error"), what="the loss message")["text"]]
        play_ttt(self, a, a_name, b, b_name, [1, 2, 3, 5, 4, 6, 8, 7, 9])
        samples["draw"] = [a.wait(is_msg(kind="game"), what="the draw message")["text"]]

        a.line("/wordle")
        a.wait(is_board("wordle"))
        a.line("/giveup")
        samples["wordleOver"] = [a.wait(is_msg("🏳️"), what="the /giveup reply")["text"]]
        a.line("/wordle")
        a.wait(is_board("wordle"))
        for word in ("aaaaa", "bbbbb", "ccccc", "ddddd", "eeeee", "fffff"):
            a.line(f"/g {word}")
        samples["wordleOver"].append(a.wait(is_msg("💀", "error"), what="the out-of-tries message")["text"])
        return samples


class TestSecurity(BridgeTestCase):
    def test_static_files_and_headers(self):
        status, headers, body = request(stack.web_port, "GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<html", body)
        self.assertIn("script-src 'self'", headers["content-security-policy"])
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertEqual(headers["referrer-policy"], "no-referrer")
        status, headers, _ = request(stack.web_port, "GET", "/app.js")
        self.assertEqual((status, headers["content-type"].split(";")[0]), (200, "text/javascript"))

    def test_every_script_module_loads(self):
        """app.js imports the other modules: each one must be served, or the whole page breaks."""
        todo, done = ["/app.js"], set()
        while todo:
            path = todo.pop()
            if path in done:
                continue
            done.add(path)
            status, headers, body = request(stack.web_port, "GET", path)
            self.assertEqual((status, headers["content-type"].split(";")[0]), (200, "text/javascript"), path)
            folder = path.rsplit("/", 1)[0]
            for target in re.findall(r'from "(\.{1,2}/[^"]+)"', body.decode("utf-8")):
                todo.append(posixpath.normpath(f"{folder}/{target}"))
        self.assertIn("/js/online.js", done)

    def test_logo_files_load(self):
        _, _, page = request(stack.web_port, "GET", "/")
        for path, kind in (("/logo.svg", "image/svg+xml"), ("/favicon-32.png", "image/png"),
                           ("/apple-touch-icon.png", "image/png")):
            status, headers, body = request(stack.web_port, "GET", path)
            self.assertEqual((status, headers["content-type"]), (200, kind), path)
            self.assertGreater(len(body), 100, path)
            self.assertIn(f'href="{path}"'.encode() if path != "/logo.svg" else b'src="/logo.svg"', page, path)
        self.assertEqual(request(stack.web_port, "GET", "/favicon.svg")[0], 404)  # the old emoji icon is gone

    def test_path_traversal_is_blocked(self):
        for path in ("/../server.py", "/%2e%2e/server.py", "/js/../../web_server.py",
                     "/..%2fweb_server.py", "//etc/passwd", "/tests/harness.py", "/js/"):
            status, _, body = request(stack.web_port, "GET", path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"import", body if isinstance(body, bytes) else b"", path)

    def test_bad_requests_are_rejected(self):
        a, _ = self.user()
        port, sid = stack.web_port, {"X-Session-Id": a.sid}
        bad_json = request(port, "POST", "/api/send", raw=b"{nope",
                           headers={**sid, "Content-Type": "application/json", "X-Hashbrown": "1"})
        self.assertEqual(bad_json[0], 400)
        self.assertEqual(a.send({"type": "admin", "text": "x"})[0], 400)
        self.assertEqual(a.send({"type": "line", "text": "x" * 501})[0], 400)
        self.assertEqual(request(port, "POST", "/api/send", body={"type": "line", "text": "hi"},
                                 headers={"X-Session-Id": "made-up"})[0], 404)
        no_header = request(port, "POST", "/api/send", raw=b'{"type":"line","text":"hi"}',
                            headers={**sid, "Content-Type": "application/json"})
        self.assertEqual(no_header[0], 403)
        other_site = request(port, "POST", "/api/send", body={"type": "line", "text": "hi"},
                             headers={**sid, "Origin": "http://evil.example"})
        self.assertEqual(other_site[0], 403)
        rebinding = request(port, "GET", "/", headers={"Host": "evil.example"})
        self.assertEqual(rebinding[0], 421)
        self.assertEqual(Stream(port, "made-up").status, 404)

    def test_oversized_body_is_refused_before_reading(self):
        a, _ = self.user()
        with socket.create_connection(("127.0.0.1", stack.web_port), timeout=5) as s:
            s.sendall(f"POST /api/send HTTP/1.1\r\nHost: 127.0.0.1:{stack.web_port}\r\n"
                      f"Content-Type: application/json\r\nX-Hashbrown: 1\r\nX-Session-Id: {a.sid}\r\n"
                      f"Content-Length: {5 * 1024 * 1024}\r\n\r\n".encode())
            self.assertIn(b" 413 ", s.recv(4096).split(b"\r\n")[0] + b" ")

    def test_session_endpoint_only_takes_a_tiny_body(self):
        status, _, _ = request(stack.web_port, "POST", "/api/session", body={"pad": "x" * 5000})
        self.assertEqual(status, 413)

    def test_newlines_cannot_split_a_message(self):
        a, _ = self.user()
        a.line("hi\n{\"type\":\"line\",\"text\":\"/daily\"}")
        msg = a.wait(is_msg(type_="chat"), what="the chat line")
        self.assertNotIn("\n", msg["text"])

    def test_session_cap(self):
        tabs = []
        try:
            while len(tabs) < 10:
                status, _, body = request(stack.web_port, "POST", "/api/session", body={})
                if status != 200:
                    break
                tabs.append(body["sid"])
            self.assertEqual(status, 503)
            self.assertLessEqual(len(tabs), 4)
        finally:
            for sid in tabs:
                request(stack.web_port, "POST", "/api/close", body={}, headers={"X-Session-Id": sid})


class TestReplay(BridgeTestCase):
    def test_reconnect_replays_only_missed_events(self):
        a, _ = self.user()
        last_id = max(e["id"] for e in a.stream.seen if e["id"])
        a.stream.close()
        time.sleep(0.2)
        a.line("/balance")
        time.sleep(0.5)
        again = Stream(stack.web_port, a.sid, last=last_id)
        self.addCleanup(again.close)
        first = again.wait_for(lambda e: e["event"] == "message", what="a replayed event")
        self.assertGreater(first["id"], last_id)
        again.wait_for(lambda e: e["event"] == "bridge" and e["data"]["event"] == "live", what="the live marker")


class TestRealDataUntouched(unittest.TestCase):
    def test_zz_real_chat_data_untouched(self):
        now = real_data.stat().st_mtime if real_data.exists() else None
        self.assertEqual(now, real_data_mtime, "the test changed your real chat_data.json!")


if __name__ == "__main__":
    unittest.main()


class TestPacketXray(BridgeTestCase):
    """🔬 Packet X-ray: while a tab asks for it, the bridge shows the raw TCP traffic it sees."""

    def test_raw_tcp_chunks_and_sent_lines_show_up_only_while_xray_is_on(self):
        a, a_name = self.user()
        a.line("before x-ray")
        a.wait(is_msg(type_="chat"), what="the chat line before x-ray")
        status, _ = a.send({"type": "xray", "on": True})
        self.assertEqual(status, 202)
        a.line("hello x-ray")
        out = a.wait(lambda e: e["data"].get("type") == "xray" and e["data"].get("dir") == "out", what="the sent line")
        self.assertIn('"hello x-ray"', out["text"])
        self.assertTrue(out["text"].endswith("\n"))           # one packet = one line
        self.assertEqual(out["bytes"], len(out["text"].encode("utf-8")))
        chunk = a.wait(lambda e: e["data"].get("type") == "xray" and e["data"].get("dir") == "in", what="a recv() chunk")
        self.assertIn("hello x-ray", chunk["text"])
        self.assertGreater(chunk["bytes"], 0)
        a.send({"type": "xray", "on": False})
        a.line("after x-ray")
        a.wait(lambda e: e["data"].get("text") == "after x-ray", what="the chat line after x-ray")
        seen = [e["data"] for e in a.stream.seen if e["data"].get("type") == "xray"]
        self.assertFalse(any("before x-ray" in d["text"] or "after x-ray" in d["text"] for d in seen))


class TestPing(BridgeTestCase):
    def test_a_ping_comes_back_as_a_pong_through_the_bridge(self):
        a, _ = self.user()
        status, _ = a.send({"type": "ping", "t": 1712.5})
        self.assertEqual(status, 202)
        self.assertEqual(a.wait(lambda e: e["data"].get("type") == "pong", what="the pong")["t"], 1712.5)


class TestChatSwitcher(BridgeTestCase):
    def test_a_tab_that_asks_for_rooms_gets_its_room_list(self):
        browser = self.tab()
        self.assertTrue(browser.auth(next(names), PASSWORD, "register", ["stream", "rooms"])["ok"])
        rooms = browser.wait(lambda e: e["data"].get("type") == "rooms", what="the room list")
        self.assertEqual(rooms["current"], "lobby")
        self.assertEqual([r["key"] for r in rooms["rooms"]], ["lobby"])


class TestTyping(BridgeTestCase):
    def test_typing_and_stopped_go_through_the_bridge(self):
        a, b = self.tab(), self.tab()
        name = next(names)
        self.assertTrue(a.auth(name, PASSWORD, "register", ["typing"])["ok"])
        self.assertTrue(b.auth(next(names), PASSWORD, "register", ["typing"])["ok"])
        self.assertEqual(a.send({"type": "typing", "extra": "dropped"})[0], 202)
        self.assertEqual(b.wait(lambda e: e["data"].get("type") == "typing", what="typing")["name"], name)
        self.assertEqual(a.send({"type": "typing_stop"})[0], 202)
        self.assertEqual(b.wait(lambda e: e["data"].get("type") == "typing_stop", what="stopped")["name"], name)


class TestReadReceipts(BridgeTestCase):
    def test_seen_goes_through_the_bridge_and_comes_back_as_a_receipt(self):
        a, _ = self.user()
        b, b_name = self.user()
        a.line(f"/send {b_name} psst")
        pm_id = b.wait(lambda e: e["data"].get("kind") == "private", what="the private message")["pm_id"]
        self.assertEqual(b.send({"type": "seen", "id": pm_id})[0], 202)
        self.assertEqual(a.wait(lambda e: e["data"].get("type") == "receipt" and e["data"].get("status") == "seen",
                                what="the seen receipt")["id"], pm_id)
        self.assertEqual(b.send({"type": "seen", "id": "seven"})[0], 400)


class TestGroupsScreen(BridgeTestCase):
    def test_the_groups_packets_go_through_the_bridge(self):
        a, _ = self.user()
        a.line("/create Bridgers")
        a.wait(is_msg("🎉"), what="the new group")
        self.assertEqual(a.send({"type": "get_groups"})[0], 202)
        cards = a.wait(lambda e: e["data"].get("type") == "groups", what="the group list")["groups"]
        self.assertEqual(cards[0]["key"], "bridgers")
        self.assertEqual(a.send({"type": "get_group", "group": "bridgers", "sneaky": 1})[0], 202)
        self.assertEqual(a.wait(lambda e: e["data"].get("type") == "group_info", what="the group")["group"]["your_role"], "owner")
        self.assertEqual(a.send({"type": "get_group", "group": ["x"]})[0], 400)
        self.assertEqual(a.send({"type": "groups_closed"})[0], 202)


class TestBigFiles(BridgeTestCase):
    """📦 A big file through the website: chunks with acks, and the chunks never go into the reload replay."""

    def test_a_chunked_file_arrives_and_its_chunks_arent_replayed(self):
        from harness import Stream
        a, b = self.tab(), self.tab()
        a_name, b_name = next(names), next(names)
        self.assertTrue(a.auth(a_name, PASSWORD, "register", ["chunks"])["ok"])
        self.assertTrue(b.auth(b_name, PASSWORD, "register", ["chunks"])["ok"])
        piece = base64.b64encode(b"x" * 10).decode()
        a.send({"type": "file_start", "id": "t1", "to": b_name, "filename": "big.bin", "size": 10, "chunks": 1})
        a.wait(lambda e: e["data"].get("type") == "file_ack" and e["data"].get("next") == 0, what="the first ack")
        a.send({"type": "file_chunk", "id": "t1", "index": 0, "data": piece})
        chunk = b.wait(lambda e: e["data"].get("type") == "file_chunk", what="the chunk")
        self.assertEqual(chunk["data"], piece)
        b.wait(lambda e: e["data"].get("type") == "file_end", what="the end")
        replay = Stream(stack.web_port, b.sid, last=0)   # what a reloaded tab gets
        self.addCleanup(replay.close)
        replay.wait_for(lambda e: e["data"].get("type") == "file_end", what="the replayed end")
        self.assertFalse(any(e["data"].get("type") == "file_chunk" for e in replay.seen))

    def test_a_bad_chunk_is_refused_by_the_bridge(self):
        a, _ = self.user()
        status, _ = a.send({"type": "file_chunk", "id": "t1", "index": 0, "data": "not base64!"})
        self.assertEqual(status, 400)
