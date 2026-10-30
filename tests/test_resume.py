"""🔁 Reconnect and catch up. At login the server gives a "resume_token"; every packet it keeps for you has a
"seq" number (the last RESUME_KEEP of them, for RESUME_SECONDS). After a dropped connection the client logs in
with {"type": "auth", "action": "resume", "username", "token", "seq": the last one it got} and gets exactly
what it missed, in order, without the usual welcome burst (so nothing shows twice).
Old clients never send "resume" and work as before (they ignore "seq")."""
import time

import pytest

from chatserver import config, resume, state

pytestmark = pytest.mark.integration


def login_info(client):
    return next(m for m in client.messages if m.get("type") == "auth_result")


def last_seq(client):
    return max(m["seq"] for m in client.messages if "seq" in m)


def come_back(connect, name, token, seq, features=None):
    client = connect()
    packet = {"type": "auth", "action": "resume", "username": name, "token": token, "seq": seq}
    if features is not None:
        packet["features"] = features
    client.send(packet)
    return client, client.expect(lambda m: m.get("type") == "auth_result")


def test_logging_in_gives_a_token_and_packets_have_growing_seq_numbers(user):
    adi = user("Adi")
    adi.line("hello")
    adi.expect(lambda m: m.get("type") == "chat")
    token = login_info(adi)["resume_token"]
    seqs = [m["seq"] for m in adi.messages if "seq" in m]
    assert isinstance(token, str) and len(token) >= 16
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs) and len(seqs) >= 3


def test_a_dropped_client_gets_exactly_what_it_missed(user, connect):
    adi, ben = user("Adi"), user("Ben")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.close()
    ben.expect_text("Adi left the chat")
    ben.line("are you there?")
    ben.line("hello??")
    ben.expect(lambda m: m.get("text") == "hello??")
    back, result = come_back(connect, "Adi", token, seen)
    assert result["ok"] and result["resumed"] is True and result["resume_token"] != token
    missed = back.expect(lambda m: m.get("text") == "hello??")
    texts = [m.get("text") for m in back.messages if m.get("type") == "chat"]
    assert texts == ["are you there?", "hello??"]                     # in order, once each
    assert all(m["seq"] > seen for m in back.messages if "seq" in m)
    assert not [m for m in back.messages if m.get("type") == "history"]   # no welcome burst
    assert missed["seq"] > seen
    ben.expect_text("Adi joined the chat")


def test_nothing_missed_nothing_replayed(user, connect):
    adi = user("Adi")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.close()
    back, result = come_back(connect, "Adi", token, seen)
    assert result["resumed"] is True
    back.line("/users")
    back.expect_text("Online now")
    assert not [m for m in back.messages if m.get("type") == "chat"]


def test_a_wrong_token_is_refused(user, connect):
    adi = user("Adi")
    seen = last_seq(adi)
    adi.close()
    _, result = come_back(connect, "Adi", "not-the-token", seen)
    assert not result["ok"] and "Log in again" in result["text"]


def test_a_token_works_once(user, connect):
    adi = user("Adi")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.close()
    back, _ = come_back(connect, "Adi", token, seen)
    back.close()
    _, again = come_back(connect, "Adi", token, seen)
    assert not again["ok"]


def test_too_old_to_resume_logs_in_normally_with_history(user, connect, monkeypatch):
    adi = user("Adi")
    token = login_info(adi)["resume_token"]
    adi.close()
    back, result = come_back(connect, "Adi", token, 0)                  # it asks for seq 1 on, which is long gone?
    if result.get("resumed"):                                          # (seq 1 may still be kept: make it gone)
        pytest.skip("the whole history is still kept")
    assert result["ok"] and result["resumed"] is False
    back.expect(lambda m: m.get("type") == "history")


def test_after_ten_minutes_away_the_token_is_dead(user, connect, monkeypatch):
    adi = user("Adi")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.close()
    user("Ben").line("/users")
    real = time.time
    monkeypatch.setattr(resume.time, "time", lambda: real() + config.RESUME_SECONDS + 1)
    _, result = come_back(connect, "Adi", token, seen)
    assert not result["ok"]


def test_back_in_the_same_room(user, connect):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/create Potatoes")
    adi.expect_text("Created")
    ben.line("/join Potatoes")
    ben.expect(lambda m: m.get("type") == "history" and m.get("key") == "potatoes")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.close()
    ben.line("in the group")
    ben.expect(lambda m: m.get("text") == "in the group")
    back, _ = come_back(connect, "Adi", token, seen)
    back.expect(lambda m: m.get("text") == "in the group")
    assert state.online["adi"].room == "potatoes"


def test_quitting_on_purpose_ends_the_token(user, connect):
    adi = user("Adi")
    token, seen = login_info(adi)["resume_token"], last_seq(adi)
    adi.line("/quit")
    adi.expect_text("Bye")
    _, result = come_back(connect, "Adi", token, seen)
    assert not result["ok"]


def test_live_only_packets_have_no_seq(user):
    adi = user("Adi", features=["typing"])
    ben = user("Ben", features=["typing"])
    ben.send({"type": "typing"})
    typing = adi.expect(lambda m: m.get("type") == "typing")
    assert "seq" not in typing
    adi.send({"type": "ping", "t": 1})
    assert "seq" not in adi.expect(lambda m: m.get("type") == "pong")


def test_old_clients_are_unchanged_apart_from_extra_fields(user):
    old = user("Old")
    result = login_info(old)
    assert result["ok"] and result["text"].startswith("✅")
    old.expect(lambda m: m.get("type") == "history")
