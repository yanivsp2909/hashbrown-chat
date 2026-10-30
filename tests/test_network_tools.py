"""🌐 Network tools for the class: /ping (round trip), /netstats (your connection) and the network lab
(the host makes the network slow or "lossy" from the server console, to see what that does)."""
import time

import pytest

from chatserver import background, config, state

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------- 🏓 ping

def test_a_ping_packet_gets_a_pong_with_the_same_number_back(user):
    adi = user("Adi")
    adi.send({"type": "ping", "t": 1234.5})
    pong = adi.expect(lambda m: m.get("type") == "pong")
    assert pong["t"] == 1234.5


def test_a_ping_without_a_number_still_gets_a_pong(user):
    adi = user("Adi")
    adi.send({"type": "ping", "t": "not a number"})
    assert "t" not in adi.expect(lambda m: m.get("type") == "pong")


def test_pings_dont_count_toward_the_spam_limit(user, monkeypatch):
    monkeypatch.setattr(config, "SPAM_LIMIT", 2)
    adi = user("Adi")
    for i in range(4):
        adi.send({"type": "ping", "t": i})
        adi.expect(lambda m: m.get("type") == "pong")
    adi.line("still allowed to talk")
    adi.expect(lambda m: m.get("type") == "chat")


def test_too_many_pings_a_second_are_ignored(user):
    adi = user("Adi")
    for i in range(config.PINGS_PER_SECOND + 5):
        adi.send({"type": "ping", "t": i})
    adi.line("/users")
    adi.expect_text("Online now")                       # everything before this has arrived
    pongs = [m for m in adi.messages if m.get("type") == "pong"]
    assert len(pongs) == config.PINGS_PER_SECOND


def test_ping_typed_by_an_old_client_gets_a_text_answer(user):
    adi = user("Adi")
    adi.line("/ping")
    adi.expect_text("🏓 Pong!")


# ---------------------------------------------------------------- 📊 netstats

def test_netstats_counts_your_packets_and_bytes(user):
    adi = user("Adi")
    adi.line("hello")
    adi.expect(lambda m: m.get("type") == "chat")
    adi.line("/netstats")
    stats = adi.expect_text("📊")["text"]
    assert "packets" in stats and "bytes" in stats
    assert "got from you: 3 packets" in stats            # login, "hello", "/netstats"


# ---------------------------------------------------------------- 🧪 network lab

def test_console_lag_loss_and_lab_off(capsys):
    background.console_command("lag 250")
    background.console_command("loss 10")
    assert (state.lab_lag_ms, state.lab_loss_percent) == (250, 10)
    background.console_command("lab")
    assert "250 ms" in capsys.readouterr().out
    background.console_command("lab off")
    assert (state.lab_lag_ms, state.lab_loss_percent) == (0, 0)
    background.console_command("lag banana")
    assert "lag <milliseconds>" in capsys.readouterr().out


def test_lag_delays_every_packet_the_server_sends(user):
    adi = user("Adi")
    state.lab_lag_ms = 300
    start = time.monotonic()
    adi.line("slow")
    adi.expect(lambda m: m.get("type") == "chat")
    assert time.monotonic() - start >= 0.3


def test_loss_makes_tcp_resend_late_but_nothing_is_lost(user, monkeypatch):
    adi = user("Adi")
    monkeypatch.setattr(background.random, "random", lambda: 0.0)   # every packet gets "lost" once
    monkeypatch.setattr(config, "LAB_RESEND_MS", 300)
    state.lab_loss_percent = 50
    start = time.monotonic()
    adi.line("one")
    adi.expect(lambda m: m.get("text") == "one")
    assert time.monotonic() - start >= 0.3              # it came, just late (like a TCP resend)


def test_lost_packets_are_late_side_by_side_not_one_after_another(user, monkeypatch):
    """Side by side: all three arrive about RESEND after they were sent. One after another would take 3 x RESEND.
    The resend is long (0.6 s) so the two cases are far apart, and a busy computer can't make the test fail."""
    adi = user("Adi")
    monkeypatch.setattr(background.random, "random", lambda: 0.0)
    monkeypatch.setattr(config, "LAB_RESEND_MS", 600)
    state.lab_loss_percent = 100
    start = time.monotonic()
    for word in ("one", "two", "three"):
        adi.line(word)
    adi.expect(lambda m: m.get("text") == "three", timeout=10)
    took = time.monotonic() - start
    assert 0.6 <= took < 1.5                       # one after another would be at least 1.8 s


# ---------------------------------------------------------------- 🧪 the lab banner

def without_seq(packet):
    return {k: v for k, v in packet.items() if k != "seq"}   # (🔁 the reconnect number)


def lab_packets(client):
    return [m for m in client.messages if m.get("type") == "lab"]


def test_everyone_hears_when_the_lab_changes(user):
    adi = user("Adi")
    background.console_command("lag 300")
    assert without_seq(adi.expect(lambda m: m.get("type") == "lab")) == {"type": "lab", "lag_ms": 300, "loss_percent": 0}
    background.console_command("loss 20")
    assert adi.expect(lambda m: m.get("type") == "lab")["loss_percent"] == 20
    background.console_command("lab off")
    assert without_seq(adi.expect(lambda m: m.get("type") == "lab", timeout=5)) == {"type": "lab", "lag_ms": 0, "loss_percent": 0}


def test_logging_in_while_the_lab_is_on_shows_it_and_not_when_off(user):
    state.lab_lag_ms, state.lab_loss_percent = 0, 15
    adi = user("Adi")
    assert adi.expect(lambda m: m.get("type") == "lab")["loss_percent"] == 15
    state.lab_loss_percent = 0
    ben = user("Ben")
    ben.line("/users")
    ben.expect_text("Online now")
    assert lab_packets(ben) == []


def test_just_looking_at_the_lab_sends_nothing(user):
    adi = user("Adi")
    background.console_command("lab")
    adi.line("/users")
    adi.expect_text("Online now")
    assert lab_packets(adi) == []
