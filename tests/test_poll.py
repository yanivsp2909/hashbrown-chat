"""📊 /poll question | option | option, then /vote, /poll (see the votes) and /endpoll."""
import pytest

from chatserver import state

pytestmark = pytest.mark.integration


def make_poll(adi, text="Pizza or falafel? | pizza | falafel"):
    adi.line(f"/poll {text}")
    return adi.expect_text("📊 Poll by Adi")


def test_a_poll_goes_to_the_room_with_its_options(user):
    adi, ben = user("Adi"), user("Ben")
    make_poll(adi)
    msg = ben.expect_text("📊 Poll by Adi")
    assert "1) pizza" in msg["text"] and "2) falafel" in msg["text"] and "/vote" in msg["text"]
    assert msg["poll"] == {"question": "Pizza or falafel?", "options": ["pizza", "falafel"]}


@pytest.mark.parametrize("text", ["", "only a question", "q | just one", "q | " + " | ".join("abcdefg")])
def test_a_poll_needs_a_question_and_2_to_6_options(user, text):
    adi = user("Adi")
    adi.line(f"/poll {text}".strip()) if text else adi.line("/poll")
    adi.expect_text("/poll question | option", kind="error")


def test_voting_and_changing_your_vote(user):
    adi, ben = user("Adi"), user("Ben")
    make_poll(adi)
    ben.line("/vote 1")
    ben.expect_text("You voted for pizza")
    ben.line("/vote 2")
    ben.expect_text("You voted for falafel")
    adi.line("/vote 2")
    adi.expect_text("You voted for falafel")
    adi.line("/poll")
    results = adi.expect_text("📊 Pizza or falafel?")["text"]
    assert "pizza: 0" in results and "falafel: 2" in results


@pytest.mark.parametrize("vote", ["/vote", "/vote 3", "/vote zero"])
def test_bad_votes_are_refused(user, vote):
    adi = user("Adi")
    make_poll(adi)
    adi.line(vote)
    adi.expect_text("/vote 1-2", kind="error")


def test_no_poll_no_vote(user):
    adi = user("Adi")
    adi.line("/vote 1")
    adi.expect_text("No poll here", kind="error")


def test_only_the_creator_can_end_it_and_everyone_sees_the_result(user):
    adi, ben = user("Adi"), user("Ben")
    make_poll(adi)
    ben.line("/vote 2")
    ben.expect_text("You voted")
    ben.line("/endpoll")
    ben.expect_text("Only Adi", kind="error")
    adi.line("/endpoll")
    final = ben.expect_text("📊 Poll closed")["text"]
    assert "falafel wins" in final
    assert "lobby" not in state.polls


def test_one_poll_per_room(user):
    adi = user("Adi")
    make_poll(adi)
    adi.line("/poll Another? | a | b")
    adi.expect_text("already a poll", kind="error")
