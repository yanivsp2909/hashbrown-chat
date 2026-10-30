"""📦 Big files (up to 15 MB) in chunks: file_start -> file_chunk, file_chunk... each answered with file_ack,
so only one chunk is on the way at a time. Only clients that said "chunks" at login can receive them."""
import base64

import pytest

from chatserver import config, state

pytestmark = pytest.mark.integration


@pytest.fixture
def chunky(connect):
    def make(name):
        client = connect()
        client.send({"type": "auth", "action": "register", "username": name, "password": "pass1234",
                     "features": ["chunks"]})
        assert client.expect(lambda m: m.get("type") == "auth_result")["ok"]
        client.expect(lambda m: m.get("type") == "history")
        return client
    return make


def start(sender, to="Ben", size=None, chunks=2, transfer_id="t1"):
    size = size if size is not None else config.CHUNK_SIZE + 10
    sender.send({"type": "file_start", "id": transfer_id, "to": to, "filename": "big.bin", "size": size, "chunks": chunks})


def chunk(sender, index, data=b"x", transfer_id="t1"):
    sender.send({"type": "file_chunk", "id": transfer_id, "index": index, "data": base64.b64encode(data).decode()})


def test_a_big_file_goes_over_chunk_by_chunk_with_acks(chunky):
    adi, ben = chunky("Adi"), chunky("Ben")
    start(adi)
    assert adi.expect(lambda m: m.get("type") == "file_ack")["next"] == 0
    begin = ben.expect(lambda m: m.get("type") == "file_start")
    assert (begin["from"], begin["filename"], begin["chunks"]) == ("Adi", "big.bin", 2)
    chunk(adi, 0, b"A" * config.CHUNK_SIZE)
    assert adi.expect(lambda m: m.get("type") == "file_ack" and m.get("next") == 1)
    chunk(adi, 1, b"B" * 10)
    piece = ben.expect(lambda m: m.get("type") == "file_chunk" and m.get("index") == 1)
    assert base64.b64decode(piece["data"]) == b"B" * 10 and piece["id"] == begin["id"]
    ben.expect(lambda m: m.get("type") == "file_end" and m.get("id") == begin["id"])
    adi.expect_text("📤 Sent big.bin")
    assert state.transfers == {}


def test_old_clients_cant_get_big_files(chunky, user):
    adi = chunky("Adi")
    user("Old")
    start(adi, to="Old")
    adi.expect_text("can't receive big files", kind="error")


@pytest.mark.parametrize("size, chunks", [(0, 1), (config.MAX_BIG_FILE + 1, 16), (100, 5)])
def test_bad_sizes_and_chunk_counts_are_refused(chunky, size, chunks):
    adi, _ = chunky("Adi"), chunky("Ben")
    start(adi, size=size, chunks=chunks)
    adi.expect_text("📦", kind="error")
    assert state.transfers == {}


def test_chunks_out_of_order_or_too_big_cancel_the_transfer(chunky):
    adi, ben = chunky("Adi"), chunky("Ben")
    start(adi)
    adi.expect(lambda m: m.get("type") == "file_ack")
    chunk(adi, 1)                                       # skipped chunk 0
    ben.expect(lambda m: m.get("type") == "file_cancel")
    adi.expect_text("cancelled", kind="error")
    assert state.transfers == {}


def test_one_transfer_at_a_time(chunky):
    adi, _ = chunky("Adi"), chunky("Ben")
    start(adi, transfer_id="one")
    adi.expect(lambda m: m.get("type") == "file_ack")
    start(adi, transfer_id="two")
    adi.expect_text("one big file at a time", kind="error")


def test_leaving_cancels_it_for_the_other_side(chunky):
    adi, ben = chunky("Adi"), chunky("Ben")
    start(adi)
    ben.expect(lambda m: m.get("type") == "file_start")
    adi.close()
    ben.expect(lambda m: m.get("type") == "file_cancel")


def test_chunks_dont_count_toward_the_spam_limit(chunky, monkeypatch):
    monkeypatch.setattr(config, "SPAM_LIMIT", 2)
    adi, ben = chunky("Adi"), chunky("Ben")
    start(adi, size=4 * config.CHUNK_SIZE, chunks=4)
    adi.expect(lambda m: m.get("type") == "file_ack")
    for i in range(4):
        chunk(adi, i, b"z" * config.CHUNK_SIZE)
        adi.expect(lambda m, i=i: m.get("type") == "file_ack" and m.get("next") == i + 1)
    ben.expect(lambda m: m.get("type") == "file_end")


# ---------------------------------------------------------------- safety (security review)

def test_a_sender_who_doesnt_wait_for_the_ack_loses_the_transfer(chunky, monkeypatch):
    adi, ben = chunky("Adi"), chunky("Ben")
    real_send = state.online["ben"].__class__.send

    def slow_send(self, obj, after=None):   # Ben's connection is slow: his chunks wait in the outbox
        if obj.get("type") == "file_chunk":
            self.held = (obj, after)
            return
        real_send(self, obj, after)
    monkeypatch.setattr(state.online["ben"].__class__, "send", slow_send)
    start(adi, size=3 * config.CHUNK_SIZE, chunks=3)
    adi.expect(lambda m: m.get("type") == "file_ack" and m.get("next") == 0)
    chunk(adi, 0)
    chunk(adi, 1)                              # without waiting for the ack of chunk 0
    adi.expect_text("cancelled", kind="error")
    assert state.transfers == {}


def test_one_big_file_at_a_time_to_each_person(chunky):
    adi, cat, _ = chunky("Adi"), chunky("Cat"), chunky("Ben")
    start(adi)
    adi.expect(lambda m: m.get("type") == "file_ack")
    start(cat, transfer_id="c1")
    cat.expect_text("already getting a big file", kind="error")


def test_starting_big_files_too_fast_is_refused(chunky):
    adi, _ = chunky("Adi"), chunky("Ben")
    start(adi, transfer_id="a")
    adi.expect(lambda m: m.get("type") == "file_ack")
    adi.send({"type": "file_cancel", "id": "a"})
    start(adi, transfer_id="b")
    adi.expect_text("Wait a moment", kind="error")


def test_a_stalled_transfer_expires(chunky, monkeypatch):
    from chatserver import transfers
    adi, ben = chunky("Adi"), chunky("Ben")
    start(adi)
    adi.expect(lambda m: m.get("type") == "file_ack")
    with state.lock:
        transfers.expire_stalled(now=10 ** 12)
    ben.expect(lambda m: m.get("type") == "file_cancel")
    assert state.transfers == {}


def test_a_chunk_that_isnt_base64_cancels_it(chunky):
    adi, ben = chunky("Adi"), chunky("Ben")
    start(adi)
    adi.expect(lambda m: m.get("type") == "file_ack")
    adi.send({"type": "file_chunk", "id": "t1", "index": 0, "data": "not base64!"})
    ben.expect(lambda m: m.get("type") == "file_cancel")
