"""
🤝 Friends: /friend add name sends a request (Accept / Decline), /friend remove name, /friends lists them.
Apps that say "friends" at login get a {"type": "friends"} packet: who your friends are, whether they're online
and what they're doing, and the requests waiting. A friend coming online gets you a small notice.
"Who can message me" has a "friends" choice.
"""
import time

import pytest

from chatserver import config, friends, state
from test_groups import GROUP, KEY, enter_room, make_group

pytestmark = pytest.mark.integration


def friends_packet(client):
    """The friends packet after one push (in the real server, background.py pushes every second)."""
    client.sync()   # (everything sent so far has been handled)
    with state.lock:
        friends.push_updates()
    with client.arrived:
        sent = [m for m in client.messages if m.get("type") == "friends"]
    return sent[-1] if sent else client.expect(lambda m: m.get("type") == "friends")


def befriend(a, b):
    a.line(f"/friend add {b.name}")
    b.expect_text(f"{a.name} wants to be friends", kind="event")
    b.line(f"/friend accept {a.name}")
    a.expect_text("are friends now")


def test_a_request_then_accept_makes_two_friends(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/friend add Ben")
    adi.expect_text("Asked Ben to be friends")
    note = ben.expect_text("Adi wants to be friends", kind="event")
    assert "/friend accept Adi" in note["text"] and "/friend decline Adi" in note["text"]
    assert state.accounts["ben"]["friend_requests"] == ["adi"]
    ben.line("/friend accept Adi")
    ben.expect_text("You and Adi are friends now")
    adi.expect_text("You and Ben are friends now")
    assert state.accounts["adi"]["friends"] == ["ben"] and state.accounts["ben"]["friends"] == ["adi"]
    assert state.accounts["ben"]["friend_requests"] == []


def test_adding_someone_who_asked_you_accepts(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/friend add Ben")
    ben.expect_text("wants to be friends")
    ben.line("/friend add Adi")
    ben.expect_text("You and Adi are friends now")


def test_decline_tells_them_and_they_cant_ask_again_right_away(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/friend add Ben")
    ben.expect_text("wants to be friends")
    ben.line("/friend decline Adi")
    ben.expect_text("said no")
    adi.expect_text("Ben said no to your friend request")
    assert state.accounts["ben"]["friend_requests"] == [] and state.accounts["adi"]["friends"] == []
    adi.line("/friend add Ben")
    adi.expect_text("Try again later", kind="error")


def test_remove_ends_it_on_both_sides(user):
    adi, ben = user("Adi"), user("Ben")
    befriend(adi, ben)
    adi.line("/friend remove Ben")
    adi.expect_text("Removed Ben from your friends")
    assert state.accounts["adi"]["friends"] == [] and state.accounts["ben"]["friends"] == []


def test_remove_also_takes_back_a_request(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/friend add Ben")
    ben.expect_text("wants to be friends")
    adi.line("/friend remove Ben")
    adi.expect_text("Took back your friend request")
    assert state.accounts["ben"]["friend_requests"] == []


@pytest.mark.parametrize("line, answer", [
    ("/friend add Adi", "yourself"), ("/friend add Nobody", "No user called"), ("/friend", "Usage: /friend"),
    ("/friend hug Ben", "Usage: /friend"), ("/friend accept Ben", "didn't ask"), ("/friend remove Ben", "isn't your friend")])
def test_the_wrong_ways(user, line, answer):
    adi, _ = user("Adi"), user("Ben")
    adi.line(line)
    adi.expect_text(answer, kind="error")


def test_asking_twice_and_already_friends(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/friend add Ben")
    ben.expect_text("wants to be friends")
    adi.line("/friend add Ben")
    adi.expect_text("Already asked", kind="error")
    ben.line("/friend accept Adi")
    adi.expect_text("are friends now")
    adi.line("/friend add Ben")
    adi.expect_text("already friends", kind="error")


def test_friends_lists_them_with_whats_waiting(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    befriend(adi, ben)
    cat.line("/friend add Adi")
    adi.expect_text("Cat wants to be friends")
    adi.line("/friends")
    text = adi.expect_text("🤝 Your friends")["text"]
    assert "🟢 Ben" in text and "Cat" in text and "/friend accept Cat" in text


def test_friends_says_when_you_have_none(user):
    adi = user("Adi")
    adi.line("/friends")
    adi.expect_text("No friends yet")


def test_a_friend_coming_online_is_a_small_notice(user):
    adi, ben = user("Adi"), user("Ben")
    befriend(adi, ben)
    ben.close()
    ben = user("Ben", action="login")
    adi.expect_text("👥 Your friend Ben is online")


def test_the_friends_packet_says_who_is_online_and_what_theyre_doing(user):
    adi = user("Adi", features=["friends"])
    ben, cat = user("Ben"), user("Cat")
    befriend(adi, ben)
    befriend(adi, cat)
    cat.close()
    make_group(ben)
    time.sleep(0.2)   # (Cat's connection closing reaches the server)
    rows = {f["name"]: f for f in friends_packet(adi)["friends"]}
    assert rows["Ben"]["online"] is True and rows["Ben"]["room"] == f"#{GROUP}"
    assert rows["Cat"]["online"] is False and rows["Cat"]["room"] == ""
    assert list(rows) == ["Ben", "Cat"]   # online first


def test_a_private_groups_name_is_hidden_from_friends_outside_it(user):
    adi = user("Adi", features=["friends"])
    ben = user("Ben")
    befriend(adi, ben)
    make_group(ben, private=True)
    rows = {f["name"]: f for f in friends_packet(adi)["friends"]}
    assert rows["Ben"]["room"] == "🔒 a private group"


def test_the_packet_has_requests_and_your_admin_groups(user):
    adi = user("Adi", features=["friends"])
    ben = user("Ben")
    make_group(adi)
    ben.line("/friend add Adi")
    adi.expect_text("Ben wants to be friends")
    packet = friends_packet(adi)
    assert packet["requests"] == ["Ben"] and packet["sent"] == []
    assert packet["groups"] == [{"key": KEY, "name": GROUP}]


def test_apps_without_the_feature_get_no_friends_packet(user):
    adi, ben = user("Adi"), user("Ben")
    befriend(adi, ben)
    with state.lock:
        friends.push_updates()
    adi.sync()
    with adi.arrived:
        assert not any(m.get("type") == "friends" for m in adi.messages)


def test_who_can_message_me_friends_only(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    befriend(adi, ben)
    adi.line("/setprofile dms friends")
    adi.expect_text("👤")
    ben.line("/send Adi hi friend")
    adi.expect_text("hi friend")
    cat.line("/send Adi hi stranger")
    cat.expect_text("only takes private messages or files from friends", kind="error")


def test_friend_requests_follow_nobody_but_friends_only_people_can_still_be_asked(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    ben.line("/setprofile dms nobody")
    ben.expect_text("👤")
    adi.line("/friend add Ben")
    adi.expect_text("doesn't take friend requests", kind="error")
    cat.line("/setprofile dms friends")
    cat.expect_text("👤")
    adi.line("/friend add Cat")
    adi.expect_text("Asked Cat")


def test_limits(user, monkeypatch):
    monkeypatch.setattr(config, "FRIEND_REQUESTS_MAX", 1)
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    ben.line("/friend add Adi")
    adi.expect_text("wants to be friends")
    cat.line("/friend add Adi")
    cat.expect_text("too many friend requests", kind="error")
    monkeypatch.setattr(config, "FRIENDS_MAX", 1)
    adi.line("/friend accept Ben")
    adi.expect_text("are friends now")
    adi.line("/friend add Cat")
    adi.expect_text("already have 1 friends", kind="error")


def test_saved_friends_are_checked_when_loading():
    accounts = {"adi": {"friends": ["ben", "ben", "ghost", "adi", 5], "friend_requests": ["cat", "ben", None]},
                "ben": {"friends": "nope", "friend_requests": []},
                "cat": {}}
    friends.clean_saved(accounts)
    assert accounts["adi"]["friends"] == ["ben"]
    assert accounts["adi"]["friend_requests"] == ["cat"]   # (not someone who's already a friend)
    assert accounts["ben"]["friends"] == ["adi"]            # friends both ways
    assert accounts["cat"] == {"friends": [], "friend_requests": []}


def test_friend_buttons_invite_to_my_group_from_anywhere(user):
    adi, ben = user("Adi"), user("Ben")
    befriend(adi, ben)
    make_group(adi, private=True)
    adi.line("/lobby")
    enter_room(adi)
    adi.send({"type": "line", "text": "/invite Ben", "group": KEY})   # 📨 the friends list's invite button
    ben.expect(lambda m: isinstance(m.get("group_invite"), dict))


# ---------------------------------------------------------------- security review fixes

def test_taking_a_request_back_doesnt_let_you_ask_again_right_away(user):
    adi, ben = user("Adi"), user("Ben")
    adi.line("/friend add Ben")
    ben.expect_text("wants to be friends")
    adi.line("/friend remove Ben")
    adi.expect_text("Took back")
    adi.line("/friend add Ben")
    adi.expect_text("Try again later", kind="error")


def test_you_can_only_have_so_many_requests_out(user, monkeypatch):
    monkeypatch.setattr(config, "FRIEND_SENT_MAX", 1)
    adi, ben, _ = user("Adi"), user("Ben"), user("Cat")
    adi.line("/friend add Ben")
    ben.expect_text("wants to be friends")
    adi.line("/friend add Cat")
    adi.expect_text("waiting for answers", kind="error")


def test_accepting_respects_the_askers_limit_too(user, monkeypatch):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    adi.line("/friend add Ben")
    ben.expect_text("wants to be friends")
    befriend(adi, cat)
    monkeypatch.setattr(config, "FRIENDS_MAX", 1)
    ben.line("/friend accept Adi")
    ben.expect_text("Adi already has 1 friends", kind="error")
    assert state.accounts["ben"]["friends"] == []


def test_one_broken_friends_list_doesnt_stop_the_others(user, monkeypatch):
    adi = user("Adi", features=["friends"])
    ben = user("Ben", features=["friends"])
    real = friends.packet
    def broken_for_adi(login, *rest):
        if login == "adi":
            raise RuntimeError("boom")
        return real(login, *rest)
    monkeypatch.setattr(friends, "packet", broken_for_adi)
    adi.sync()
    ben.sync()
    with state.lock:
        friends.push_updates()
    ben.expect(lambda m: m.get("type") == "friends")


def test_one_sided_data_doesnt_crash_remove(user):
    adi, _ = user("Adi"), user("Ben")
    with state.lock:
        state.accounts["adi"]["friends"].append("ben")   # (only one side: bad data)
    adi.line("/friend remove Ben")
    adi.expect_text("Removed Ben")
    assert state.accounts["adi"]["friends"] == []
