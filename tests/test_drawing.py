"""🎨 The drawing game: /draw starts a round in your room; you get a secret word (privately) and draw it.
Every brush stroke is a small {"type": "stroke"} packet the server passes to the room (only the drawer may send
them). The others guess in the chat: the server checks, so the word never reaches them before the round ends.
The first right guess wins DRAW_GUESS_PRIZE, the drawer gets DRAW_DRAWER_PRIZE. Old clients get text."""
import time

import pytest

from chatserver import config, drawing, state

pytestmark = pytest.mark.integration


def start(adi, word="cat"):
    adi.line("/draw")
    secret = adi.expect(lambda m: m.get("kind") == "private" and "Your word" in m.get("text", ""))
    state.drawings["lobby"]["word"] = word        # a known word for the test
    state.drawings["lobby"]["started"] -= 60      # (a guess in the first DRAW_MIN_SECONDS wins nothing)
    return secret


def stroke(points=((10, 10), (500, 500)), **extra):
    return {"type": "stroke", "points": [list(p) for p in points], "color": 0, "size": 2, **extra}


def test_starting_tells_the_room_but_only_the_drawer_gets_the_word(user):
    adi, ben = user("Adi", features=["draw"]), user("Ben", features=["draw"])
    start(adi)
    news = ben.expect_text("🎨 Adi is drawing")
    round_info = ben.expect(lambda m: m.get("type") == "draw_round")
    assert round_info["state"] == "started" and round_info["drawer"] == "Adi" and "word" not in round_info
    assert "letters" in news["text"]
    assert not [m for m in ben.messages if "Your word" in str(m.get("text", ""))]


def test_strokes_go_to_the_room_and_only_from_the_drawer(user):
    adi, ben = user("Adi", features=["draw"]), user("Ben", features=["draw"])
    start(adi)
    adi.send(stroke())
    got = ben.expect(lambda m: m.get("type") == "stroke")
    assert got["points"] == [[10, 10], [500, 500]] and got["by"] == "Adi"
    ben.send(stroke(points=((1, 1), (2, 2))))
    adi.send(stroke(points=((3, 3), (4, 4))))
    ben.expect(lambda m: m.get("type") == "stroke" and m["points"] == [[3, 3], [4, 4]])
    assert not [m for m in adi.messages if m.get("type") == "stroke" and m["points"] == [[1, 1], [2, 2]]]


@pytest.mark.parametrize("bad", [
    {"points": "nope"}, {"points": [[1, 2, 3]]}, {"points": [[-5, 2]]}, {"points": [[5000, 2]]},
    {"points": [[1, 1]] * (64 + 1)}, {"color": 99}, {"size": 9},
])
def test_bad_strokes_are_dropped(user, bad):
    adi, ben = user("Adi", features=["draw"]), user("Ben", features=["draw"])
    start(adi)
    adi.send({**stroke(), **bad})
    adi.send(stroke(points=((7, 7), (8, 8))))
    first = ben.expect(lambda m: m.get("type") == "stroke")
    assert first["points"] == [[7, 7], [8, 8]]


def test_the_right_guess_wins_and_is_never_posted(user):
    adi, ben, cat = user("Adi", features=["draw"]), user("Ben"), user("Cat")
    start(adi)
    before = (state.accounts["ben"]["tokens"], state.accounts["adi"]["tokens"])
    ben.line("dog")
    cat.expect(lambda m: m.get("type") == "chat" and m.get("text") == "dog")      # wrong guesses are chat
    ben.line("  CAT ")
    news = cat.expect_text("guessed it")
    assert "CAT" in news["text"] and "Ben" in news["text"]
    assert not [m for m in cat.messages if m.get("type") == "chat" and "cat" in m.get("text", "").lower()]
    assert state.accounts["ben"]["tokens"] == before[0] + config.DRAW_GUESS_PRIZE
    assert state.accounts["adi"]["tokens"] == before[1] + config.DRAW_DRAWER_PRIZE
    assert "lobby" not in state.drawings


def test_the_drawer_cant_win_by_typing_the_word(user):
    adi, ben = user("Adi"), user("Ben")
    start(adi)
    adi.line("cat")
    adi.expect_text("Don't say the word", kind="error")
    assert "lobby" in state.drawings


def test_one_round_per_room_and_you_need_company(user):
    adi = user("Adi")
    adi.line("/draw")
    adi.expect_text("at least 2", kind="error")
    ben = user("Ben")
    start(adi)
    ben.line("/draw")
    ben.expect_text("already drawing", kind="error")


def test_time_runs_out_and_the_word_is_shown(user):
    adi, ben = user("Adi", features=["draw"]), user("Ben", features=["draw"])
    start(adi)
    state.drawings["lobby"]["until"] = 0
    with state.lock:
        drawing.end_due()
    ben.expect_text("Time's up")
    ended = ben.expect(lambda m: m.get("type") == "draw_round" and m.get("state") == "ended")
    assert ended["word"] == "cat"


def test_the_drawer_can_give_up(user):
    adi, ben = user("Adi"), user("Ben")
    start(adi)
    adi.line("/draw stop")
    ben.expect_text("gave up")
    assert "lobby" not in state.drawings


def test_someone_coming_in_gets_the_drawing_so_far(user):
    adi, ben = user("Adi", features=["draw"]), user("Ben", features=["draw"])
    start(adi)
    adi.send(stroke())
    ben.expect(lambda m: m.get("type") == "stroke")
    cat = user("Cat", features=["draw"])
    joined = cat.expect(lambda m: m.get("type") == "draw_round")
    assert joined["state"] == "started" and joined["strokes"][0]["points"] == [[10, 10], [500, 500]]


def test_strokes_dont_count_as_spam_but_have_their_own_limit(user, monkeypatch):
    monkeypatch.setattr(config, "SPAM_LIMIT", 2)
    adi, ben = user("Adi", features=["draw"]), user("Ben", features=["draw"])
    start(adi)
    for i in range(config.DRAW_STROKES_PER_SECOND + 10):
        adi.send(stroke(points=((i, i), (i + 1, i + 1))))
    adi.line("still talking")
    ben.expect(lambda m: m.get("text") == "still talking")
    assert len([m for m in ben.messages if m.get("type") == "stroke"]) <= config.DRAW_STROKES_PER_SECOND


# ---------------------------------------------------------------- code review: no farming, no stuck rounds

def test_a_too_fast_guess_wins_nothing(user):
    adi, ben = user("Adi"), user("Ben")
    start(adi)
    state.drawings["lobby"]["started"] = time.time()
    before = state.accounts["ben"]["tokens"]
    ben.line("cat")
    ben.expect_text("Too fast for a prize")
    assert state.accounts["ben"]["tokens"] == before


def test_the_same_person_waits_before_starting_again(user):
    adi, ben = user("Adi"), user("Ben")
    start(adi)
    adi.line("/draw stop")
    ben.expect_text("gave up")
    adi.line("/draw")
    adi.expect_text("another round in", kind="error")


def test_the_round_ends_when_the_drawer_leaves_the_room(user):
    adi, ben = user("Adi"), user("Ben")
    start(adi)
    adi.line("/create Potatoes")
    ben.expect_text("Adi left. The word was CAT")
    assert "lobby" not in state.drawings


def test_the_end_packet_doesnt_carry_the_drawing(user):
    adi, ben = user("Adi", features=["draw"]), user("Ben", features=["draw"])
    start(adi)
    adi.send(stroke())
    ben.expect(lambda m: m.get("type") == "stroke")
    adi.line("/draw stop")
    ended = ben.expect(lambda m: m.get("type") == "draw_round" and m.get("state") == "ended")
    assert "strokes" not in ended and ended["word"] == "cat"
