"""Hashbrown streaming: pieces for clients that ask for them, one full message for everybody else.
Always against the fake Foundry in tests/helpers.py (it speaks the openai package's protocol)."""
import json

import pytest

from chatserver import auth, config, hashbrown_ai, state

pytestmark = pytest.mark.integration

PIECES = ["Hello ", "there, ", "this is ", "Hashbrown 🥔"]
FULL = "".join(PIECES)


def is_stream(msg):
    return msg.get("type") == "stream"


def is_hashbrown_chat(msg):
    return msg.get("type") == "chat" and msg.get("name") == "Hashbrown"


def is_thinking(msg):
    return msg.get("type") == "msg" and "thinking" in msg.get("text", "")


def stream_until_final(client, final_check=is_hashbrown_chat):
    """(the stream packets, the final message) that this client receives for one question."""
    packets = []
    while True:
        msg = client.expect(lambda m: is_stream(m) or final_check(m))
        if is_stream(msg):
            packets.append(msg)
        else:
            return packets, msg


# ---------------------------------------------------------------- the features field

@pytest.mark.parametrize("value, expected", [
    (["stream"], {"stream"}),
    (["stream", "x" * 20], {"stream", "x" * 20}),
    (None, set()),
    ("stream", set()),
    ({"stream": True}, set()),
    ([], set()),
    (["stream", 5], set()),
    (["x" * 21], set()),
    ([f"f{i}" for i in range(9)], set()),
])
def test_features_are_validated(value, expected):
    assert auth.clean_features(value) == expected


def test_the_client_remembers_its_features(user):
    user("Adi", features=["stream"])
    user("Ben")
    assert state.online["adi"].features == {"stream"}
    assert state.online["ben"].features == set()


# ---------------------------------------------------------------- the stream itself

def test_streaming_client_gets_pieces_then_the_final_message(user, fake_hashbrown):
    adi = user("Adi", features=["stream"])
    fake_hashbrown.pieces = PIECES
    adi.line("@hashbrown hi")
    thinking = adi.expect(is_thinking)
    packets, final = stream_until_final(adi)
    assert packets, "no stream packets"
    assert "".join(p["append"] for p in packets) == FULL
    first = packets[0]
    assert first["type"] == "stream" and first["name"] == "Hashbrown" and first["badge"] == "🥔"
    assert len(first["time"]) == 5
    assert first["replaces"] == thinking["temp_id"]            # the thinking card becomes the live bubble
    assert all("replaces" not in p for p in packets[1:])
    assert {p["stream_id"] for p in packets} == {final["stream_id"]}
    assert final["done"] is True and final["replaces"] == thinking["temp_id"]
    assert final["text"] == FULL and final["id"]


def test_old_client_gets_only_the_full_message(user, fake_hashbrown):
    adi, ben = user("Adi", features=["stream"]), user("Ben")
    fake_hashbrown.pieces = PIECES
    adi.line("@hashbrown hi")
    ben.expect(is_thinking)
    final = ben.expect(is_hashbrown_chat)
    assert final["text"] == FULL
    ben.sync()
    assert not any(is_stream(m) for m in ben.messages)
    assert any(is_stream(m) for m in adi.messages)             # the streaming client did get pieces


def test_the_whole_room_streams_but_other_rooms_do_not(user, fake_hashbrown):
    adi, ben, cara = user("Adi"), user("Ben", features=["stream"]), user("Cara", features=["stream"])
    cara.line("/create Elsewhere")
    cara.expect_text("Elsewhere")
    fake_hashbrown.pieces = PIECES
    adi.line("@hashbrown hi")
    packets, final = stream_until_final(ben)
    assert "".join(p["append"] for p in packets) == FULL and final["done"]
    cara.sync()
    assert not any(is_stream(m) or is_hashbrown_chat(m) for m in cara.messages)


def test_ask_streams_only_to_the_asker(user, fake_hashbrown):
    adi, ben = user("Adi", features=["stream"]), user("Ben", features=["stream"])
    fake_hashbrown.pieces = PIECES
    adi.line("/ask hi")
    thinking = adi.expect(is_thinking)
    packets, final = stream_until_final(adi, lambda m: m.get("kind") == "private")
    assert "".join(p["append"] for p in packets) == FULL
    assert final["text"] == f"🥔 Hashbrown (only you): {FULL}"
    assert final["done"] is True and final["stream_id"] == packets[0]["stream_id"]
    assert final["replaces"] == thinking["temp_id"]
    ben.sync()
    assert not any(is_stream(m) for m in ben.messages)


def test_the_final_message_is_the_cleaned_text_and_history_stays_plain(user, fake_hashbrown):
    from chatserver import history
    adi = user("Adi", features=["stream"])
    fake_hashbrown.pieces = ["**Hi** ", "there"]
    adi.line("@hashbrown hi")
    packets, final = stream_until_final(adi)
    assert "".join(p["append"] for p in packets) == "**Hi** there"   # live pieces are raw
    assert "**" not in final["text"]                                  # the final goes through clean_answer
    assert all("stream_id" not in m and "done" not in m for m in history.recent("lobby"))


def test_many_tiny_pieces_are_sent_in_batches(user, fake_hashbrown):
    adi = user("Adi", features=["stream"])
    fake_hashbrown.pieces = ["a"] * 200
    adi.line("@hashbrown hi")
    packets, final = stream_until_final(adi)
    assert "".join(p["append"] for p in packets) == "a" * 200
    assert 1 < len(packets) < 30


def test_a_runaway_answer_is_cut_off_early(user, fake_hashbrown, monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_MAX_CHARS", 100)
    monkeypatch.setattr(config, "HASHBROWN_MAX_CODE_LINES", 5)
    adi = user("Adi", features=["stream"])
    fake_hashbrown.pieces = ["word " * 20] * 50       # 5000 characters in 50 pieces
    adi.line("@hashbrown hi")
    packets, final = stream_until_final(adi)
    streamed = sum(len(p["append"]) for p in packets)
    assert streamed < 5000                            # we stopped reading
    assert len(final["text"]) <= config.HASHBROWN_MAX_CHARS + 60   # and the final is the shortened text
    assert final["done"] is True


# ---------------------------------------------------------------- a stream that breaks

@pytest.mark.parametrize("how", ["failed", "error", "incomplete", "drop"])
def test_a_broken_stream_sends_failed_then_the_refund(user, fake_hashbrown, how):
    adi = user("Adi", features=["stream"])
    fake_hashbrown.pieces = PIECES
    fake_hashbrown.break_after = 2
    fake_hashbrown.break_with = how
    adi.line("@hashbrown hi")
    thinking = adi.expect(is_thinking)
    first = adi.expect(is_stream)
    failed = adi.expect(lambda m: is_stream(m) and m.get("failed"))
    assert failed["done"] is True and failed["stream_id"] == first["stream_id"]
    error = adi.expect_text("refunded", kind="error")
    assert error["replaces"] == thinking["temp_id"]
    adi.sync()
    assert state.accounts["adi"]["tokens"] == config.START_TOKENS
    assert state.hashbrown_today["adi"][1] == 0
    assert not any(is_hashbrown_chat(m) for m in adi.messages)


def test_a_broken_stream_does_not_bother_old_clients(user, fake_hashbrown):
    adi, ben = user("Adi", features=["stream"]), user("Ben")
    fake_hashbrown.pieces = PIECES
    fake_hashbrown.break_after = 1
    adi.line("@hashbrown hi")
    ben.expect_text("refunded", kind="error")
    assert not any(is_stream(m) for m in ben.messages)


def test_a_private_stream_that_breaks_refunds_the_asker(user, fake_hashbrown):
    adi = user("Adi", features=["stream"])
    fake_hashbrown.pieces = PIECES
    fake_hashbrown.break_after = 1
    adi.line("/ask hi")
    adi.expect(lambda m: is_stream(m) and m.get("failed"))
    adi.expect_text("refunded", kind="error")
    adi.sync()
    assert state.accounts["adi"]["tokens"] == config.START_TOKENS


# ---------------------------------------------------------------- reasoning fallback, still working

def test_reasoning_400_retries_once_without_it_and_streams(user, fake_hashbrown, capsys):
    adi = user("Adi", features=["stream"])
    fake_hashbrown.reject_reasoning = True
    fake_hashbrown.pieces = PIECES
    adi.line("@hashbrown hi")
    packets, final = stream_until_final(adi)
    assert final["text"] == FULL
    bodies = [body for _, body in fake_hashbrown.requests]
    assert "reasoning" in bodies[0] and "reasoning" not in bodies[1]
    assert state.hashbrown_no_reasoning is True
    assert capsys.readouterr().out.count("doesn't support reasoning") == 1


def test_a_400_without_reasoning_is_an_error(user, fake_hashbrown, monkeypatch):
    monkeypatch.setattr(config, "HASHBROWN_REASONING", "")
    adi = user("Adi")
    fake_hashbrown.status = 400
    adi.line("@hashbrown hi")
    adi.expect_text("refunded", kind="error")
    assert len(fake_hashbrown.requests) == 1


def test_the_key_never_reaches_the_log(user, fake_hashbrown, capsys):
    adi = user("Adi")
    fake_hashbrown.status = 401
    adi.line("@hashbrown hi")
    adi.expect_text("refunded", kind="error")
    out = capsys.readouterr().out
    assert "test-key" not in out
    assert "AuthenticationError" in out and "401" in out


# ---------------------------------------------------------------- no openai package

def settings_file(port=1):
    with open(config.HASHBROWN_CONFIG, "w", encoding="utf-8") as f:
        json.dump({"endpoint": f"http://127.0.0.1:{port}", "deployment": "fake-model", "api_key": "test-key"}, f)


def test_without_the_openai_package_hashbrown_is_off_with_one_clear_line(monkeypatch, capsys):
    settings_file()
    monkeypatch.setattr(hashbrown_ai, "import_openai", lambda: None)
    assert hashbrown_ai.load_hashbrown() is None
    lines = [line for line in capsys.readouterr().out.splitlines() if "[HASHBROWN]" in line]
    assert lines == ["[HASHBROWN] 🥔 Hashbrown needs the openai package: pip install -r requirements.txt"]


def test_with_the_package_hashbrown_wakes_up_and_uses_the_v1_base_url(capsys):
    settings_file(port=1234)
    settings = hashbrown_ai.load_hashbrown()
    assert settings["base_url"] == "http://127.0.0.1:1234/openai/v1"
    assert "Awake" in capsys.readouterr().out


def test_asking_while_the_package_is_missing_refunds(user, fake_hashbrown, monkeypatch):
    adi = user("Adi")
    monkeypatch.setattr(hashbrown_ai, "import_openai", lambda: None)
    adi.line("@hashbrown hi")
    adi.expect_text("refunded", kind="error")
    assert fake_hashbrown.requests == []


def test_requirements_file_pins_openai_below_2():
    with open(config.BASE_DIR + "/requirements.txt", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    assert lines == ["openai>=1.66,<2"]
