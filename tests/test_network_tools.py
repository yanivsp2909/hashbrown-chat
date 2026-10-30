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
