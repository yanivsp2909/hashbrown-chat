"""📎 File offers: a client that said "offers" at login is asked first ("📎 Adi wants to send you a.txt (1 KB)"),
and the file only goes through after /accept. /decline says no; offers expire after OFFER_SECONDS.
Old clients that didn't say "offers" keep getting files straight away, as before."""
import base64
import time

import pytest

from chatserver import config, offers, state, transfers

pytestmark = pytest.mark.integration

SMALL = base64.b64encode(b"hello there").decode()


@pytest.fixture
def asker(connect):
    """asker("Ben") -> a client that understands offers (and big files)."""
    def make(name, features=("offers", "chunks")):
        client = connect()
        client.send({"type": "auth", "action": "register", "username": name, "password": "pass1234",
                     "features": list(features)})
        assert client.expect(lambda m: m.get("type") == "auth_result")["ok"]
        client.expect(lambda m: m.get("type") == "history")
        return client
    return make


def send_small(sender, to="Ben", filename="a.txt"):
    sender.send({"type": "file", "to": to, "filename": filename, "data": SMALL})


def offer_of(client):
    return client.expect(lambda m: m.get("offer"))


def files_of(client):
    return [m for m in client.messages if m.get("type") == "file"]


def test_a_small_file_waits_for_accept(user, asker):
    adi, ben = user("Adi"), asker("Ben")
    send_small(adi)
    offer = offer_of(ben)
    assert offer["text"].startswith("📎 Adi wants to send you a.txt (1 KB)") and "/accept file" in offer["text"]
    assert offer["offer"]["from"] == "Adi" and offer["offer"]["filename"] == "a.txt"
    adi.expect_text("Waiting for Ben")
    assert files_of(ben) == []
    ben.line("/accept")
    got = ben.expect(lambda m: m.get("type") == "file")
    assert (got["from"], got["filename"], got["data"]) == ("Adi", "a.txt", SMALL)
    adi.expect_text("📤 Sent a.txt")


def test_decline_tells_the_sender_and_sends_nothing(user, asker):
    adi, ben = user("Adi"), asker("Ben")
    send_small(adi)
    offer_of(ben)
    ben.line("/decline Adi")
    adi.expect_text("declined", kind="error")
    ben.line("/accept file")
    ben.expect_text("No file offers", kind="error")
    assert files_of(ben) == []


def test_old_clients_still_get_files_straight_away(user):
    adi, old = user("Adi"), user("Old")
    send_small(adi, to="Old")
    assert old.expect(lambda m: m.get("type") == "file")["data"] == SMALL


def test_offers_expire(user, asker):
    adi, ben = user("Adi"), asker("Ben")
    send_small(adi)
    offer_of(ben)
    with state.lock:
        offers.expire(now=time.time() + config.OFFER_SECONDS + 1)
    adi.expect_text("didn't answer", kind="error")
    ben.line("/accept file")
    ben.expect_text("No file offers", kind="error")


def test_a_waiting_challenge_wins_over_a_file_unless_you_say_file(user, asker):
    """Security review: a file sent last must not steal the /accept you meant for a game."""
    adi, ben = user("Adi"), asker("Ben")
    adi.line("/challenge Ben ttt")
    ben.expect_text("challenges you")
    send_small(adi)
    offer_of(ben)
    ben.line("/accept")                             # the game, even though the file came last
    ben.expect(lambda m: m.get("kind") == "board")
    assert files_of(ben) == []
    ben.line("/accept file")
    ben.expect(lambda m: m.get("type") == "file")


def test_accept_file_with_the_offer_number(user, asker):
    adi, cat, ben = user("Adi"), user("Cat"), asker("Ben")
    send_small(adi, filename="one.txt")
    first = offer_of(ben)["offer"]["id"]
    send_small(cat, filename="two.txt")
    offer_of(ben)
    ben.line(f"/accept file {first}")
    assert ben.expect(lambda m: m.get("type") == "file")["filename"] == "one.txt"


def test_at_most_a_few_offers_wait_for_one_person(user, asker):
    ben = asker("Ben")
    senders = [user(f"Adi{i}") for i in range(config.OFFERS_WAITING_MAX + 1)]
    for sender in senders[:-1]:
        send_small(sender)
        sender.expect_text("Waiting for Ben")       # one after another, so the last one is surely the extra
    send_small(senders[-1])
    senders[-1].expect_text("already has", kind="error")
    assert len([o for o in state.offers.values() if o["to"] == "ben"]) == config.OFFERS_WAITING_MAX


def test_one_waiting_offer_per_sender(user, asker):
    adi, _, _ = user("Adi"), asker("Ben"), asker("Cat")
    send_small(adi)
    adi.expect_text("Waiting for Ben")
    send_small(adi, to="Cat")
    adi.expect_text("Wait until", kind="error")


def test_the_sender_leaving_takes_the_offer_away(user, asker):
    adi, ben = user("Adi"), asker("Ben")
    send_small(adi)
    offer_of(ben)
    adi.close()
    ben.expect_text("Adi left", kind="error")
    assert state.offers == {}


# ---------------------------------------------------------------- 📦 big files are offered too

def start_big(sender, to="Ben"):
    sender.send({"type": "file_start", "id": "t1", "to": to, "filename": "big.bin",
                 "size": config.CHUNK_SIZE + 10, "chunks": 2})


def test_a_big_file_starts_only_after_accept(asker):
    adi, ben = asker("Adi"), asker("Ben")
    start_big(adi)
    offer = offer_of(ben)
    assert "(1.0 MB)" in offer["text"]
    assert not [m for m in ben.messages if m.get("type") == "file_start"]
    assert not [m for m in adi.messages if m.get("type") == "file_ack"]
    ben.line("/accept")
    ben.expect(lambda m: m.get("type") == "file_start")
    assert adi.expect(lambda m: m.get("type") == "file_ack")["next"] == 0


def test_declining_a_big_file_cancels_it_for_the_sender(asker):
    adi, ben = asker("Adi"), asker("Ben")
    start_big(adi)
    offer_of(ben)
    ben.line("/decline")
    assert adi.expect(lambda m: m.get("type") == "file_cancel")["id"] == "t1"
    assert state.transfers == {}


def test_a_waiting_big_file_doesnt_count_as_stalled(asker):
    adi, ben = asker("Adi"), asker("Ben")
    start_big(adi)
    offer_of(ben)
    with state.lock:
        transfers.expire_stalled(now=time.time() + config.BIG_FILE_STALL + 1)
    assert len(state.transfers) == 1


def test_the_sender_cancelling_a_waiting_big_file_removes_the_offer(asker):
    adi, ben = asker("Adi"), asker("Ben")
    start_big(adi)
    offer_of(ben)
    adi.send({"type": "file_cancel", "id": "t1"})
    ben.expect_text("cancelled", kind="error")
    assert state.offers == {} and state.transfers == {}


def test_all_waiting_small_files_together_have_a_cap(user, asker, monkeypatch):
    monkeypatch.setattr(config, "OFFERS_BYTES_MAX", len(SMALL) + 10)
    adi, cat, _ = user("Adi"), user("Cat"), asker("Ben")
    send_small(adi)
    adi.expect_text("Waiting for Ben")
    send_small(cat)
    cat.expect_text("Too many files are waiting", kind="error")


def test_a_waiting_big_file_doesnt_block_other_senders(asker):
    adi, cat, ben = asker("Adi"), asker("Cat"), asker("Ben")
    start_big(adi)
    offer_of(ben)
    cat.send({"type": "file_start", "id": "c1", "to": "Ben", "filename": "two.bin",
              "size": config.CHUNK_SIZE + 10, "chunks": 2})
    cat.expect_text("Waiting for Ben")


def test_logging_in_again_ends_the_old_windows_offers(user, asker, connect):
    adi, ben = user("Adi"), asker("Ben")
    send_small(adi)
    offer_of(ben)
    user("Adi", action="login")                     # the same account from a new window
    assert state.offers == {}
