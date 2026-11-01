"""
📨 Group invites: an admin types /invite name in the group's chat (or uses the Groups screen). The invited person
gets an invite card (a msg with an optional "group_invite" field) with Accept (/join name) and Decline
(/invites decline name). It works for private groups too, with no join request, and ends after 24 hours.
"""
import time

import pytest

from chatserver import config, group_view, invites, state
from test_groups import GROUP, KEY, enter_room, give_tokens, group_with_members, make_group

pytestmark = pytest.mark.integration


def is_invite(m):
    return m.get("type") == "msg" and isinstance(m.get("group_invite"), dict)


def closed(why):
    return lambda m: m.get("type") == "invite_closed" and m.get("group") == KEY and m.get("why") == why


def private_group_and_ben(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, private=True)
    return adi, ben


def test_an_admin_invites_and_the_invite_card_says_how_to_answer(user):
    adi, ben = private_group_and_ben(user)
    adi.line("/invite Ben")
    adi.expect_text("📨 Invited Ben")
    card = ben.expect(is_invite)
    invite = card["group_invite"]
    assert invite["group"] == KEY and invite["name"] == GROUP and invite["from"] == "Adi"
    assert invite["expires"] > time.time() + 23 * 3600
    assert card["kind"] == "event" and f"/join {GROUP}" in card["text"] and f"/invites decline {GROUP}" in card["text"]


def test_accepting_lets_you_into_a_private_group_without_a_request(user):
    adi, ben = private_group_and_ben(user)
    adi.line("/invite Ben")
    ben.expect(is_invite)
    ben.line(f"/join {GROUP}")
    ben.expect(closed("accepted"))                        # the card goes, then you're in the room
    enter_room(ben)
    assert "ben" in state.groups[KEY]["members"] and "ben" not in state.groups[KEY]["requests"]
    assert state.groups[KEY]["invites"] == {}
    adi.expect_text("Ben joined")


def test_an_invite_also_answers_a_waiting_join_request(user):
    adi, ben = private_group_and_ben(user)
    ben.line(f"/join {GROUP}")
    ben.expect_text("Request sent")
    adi.line("/invite Ben")
    ben.expect(is_invite)
    ben.line(f"/join {GROUP}")
    enter_room(ben)
    assert state.groups[KEY]["requests"] == []


def test_declining_tells_the_admin_and_closes_the_card(user):
    adi, ben = private_group_and_ben(user)
    adi.line("/invite Ben")
    ben.expect(is_invite)
    ben.line(f"/invites decline {GROUP}")
    ben.expect(closed("declined"))
    adi.expect_text("Ben said no to the invite")
    assert state.groups[KEY]["invites"] == {}
    ben.line(f"/join {GROUP}")                            # no invite any more: the usual request
    ben.expect_text("Request sent")


def test_invites_lists_yours(user):
    adi, ben = private_group_and_ben(user)
    ben.line("/invites")
    ben.expect_text("No group invites")
    adi.line("/invite Ben")
    ben.expect(is_invite)
    ben.line("/invites")
    text = ben.expect_text("📨 Your group invites")["text"]
    assert GROUP in text and "Adi" in text and "24 h" in text


def test_only_admins_can_invite(user):
    adi, ben, cat = group_with_members(user, "Adi", "Ben", "Cat")
    user("Dan")
    ben.line("/invite Dan")
    ben.expect_text("Only group admins can invite", kind="error")
    adi.line("/promote Ben")
    adi.expect_text("is now an admin")
    ben.line("/invite Dan")
    ben.expect_text("📨 Invited Dan")


def test_invite_is_a_group_command(user):
    adi, ben = private_group_and_ben(user)
    adi.line("/lobby")
    enter_room(adi)
    adi.line("/invite Ben")
    adi.expect_text("Open the group's chat to use /invite", kind="error")


@pytest.mark.parametrize("who, answer", [("Adi", "yourself"), ("Ben", "already in"), ("Nobody", "No user called"),
                                         ("", "Usage: /invite name")])
def test_who_you_cant_invite(user, who, answer):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line(f"/invite {who}".strip())
    adi.expect_text(answer, kind="error")


def test_banned_people_cant_be_invited_and_a_ban_ends_an_invite(user):
    adi, ben = private_group_and_ben(user)
    adi.line("/invite Ben")
    ben.expect(is_invite)
    adi.line("/ban Ben")
    ben.expect(closed("gone"))
    assert state.groups[KEY]["invites"] == {}
    adi.line("/invite Ben")
    adi.expect_text("is banned", kind="error")


def test_an_invite_ends_after_24_hours(user):
    adi, ben = private_group_and_ben(user)
    adi.line("/invite Ben")
    ben.expect(is_invite)
    with state.lock:
        state.groups[KEY]["invites"]["ben"]["at"] -= config.GROUP_INVITE_HOURS * 3600 + 1
    ben.line(f"/join {GROUP}")
    ben.expect_text("Request sent")                       # the old invite doesn't count any more
    assert "ben" not in state.groups[KEY]["members"]
    assert state.groups[KEY]["invites"] == {}


def test_a_demoted_admins_invite_stops_working(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    make_group(adi, private=True)
    with state.lock:
        state.groups[KEY]["members"].append("ben")
        state.groups[KEY]["admins"].append("ben")
    ben.line(f"/join {GROUP}")
    enter_room(ben)
    ben.line("/invite Cat")
    cat.expect(is_invite)
    adi.line("/demote Ben")
    adi.expect_text("no longer an admin")
    cat.line(f"/join {GROUP}")
    cat.expect_text("Request sent")


def test_someone_offline_finds_the_invite_when_they_log_in(user):
    ben = user("Ben")
    ben.close()
    adi = user("Adi")
    make_group(adi, private=True)
    adi.line("/invite Ben")
    adi.expect_text("📨 Invited Ben")
    ben = user("Ben", action="login")
    assert ben.expect(is_invite)["group_invite"]["group"] == KEY


def test_who_can_message_me_covers_invites(user):
    adi, ben = private_group_and_ben(user)
    ben.line("/setprofile dms nobody")
    ben.expect_text("👤")
    adi.line("/invite Ben")
    adi.expect_text("doesn't take group invites", kind="error")
    assert state.groups[KEY]["invites"] == {}


def test_a_group_has_at_most_so_many_waiting_invites(user, monkeypatch):
    monkeypatch.setattr(config, "GROUP_INVITES_MAX", 1)
    adi, _, _ = user("Adi"), user("Ben"), user("Cat")
    make_group(adi, private=True)
    adi.line("/invite Ben")
    adi.expect_text("📨 Invited Ben")
    adi.line("/invite Cat")
    adi.expect_text("waiting invites", kind="error")


def test_the_groups_screen_invite_button_works_from_the_lobby(user):
    adi, ben = private_group_and_ben(user)
    adi.line("/lobby")
    enter_room(adi)
    adi.send({"type": "line", "text": "/invite Ben", "group": KEY})
    adi.expect_text("📨 Invited Ben")
    ben.expect(is_invite)


def test_admins_see_waiting_invites_on_the_groups_screen(user):
    adi, ben = private_group_and_ben(user)
    adi.line("/invite Ben")
    ben.expect(is_invite)
    with state.lock:
        details = group_view.details(KEY, "adi")
    assert details["admin"]["invites"] == [{"name": "Ben", "hours_left": 24}]


def test_disbanding_ends_the_invites(user):
    adi, ben = private_group_and_ben(user)
    give_tokens("Adi", 100)
    adi.line("/invite Ben")
    ben.expect(is_invite)
    adi.line("/disband")
    ben.expect(closed("gone"))


def test_saved_invites_are_checked_when_loading():
    now = time.time()
    saved = {"ben": {"by": "adi", "at": now}, "cat": {"by": 5, "at": now}, "dan": "nope", 7: {"by": "adi", "at": now},
             "eve": {"by": "adi", "at": "soon"}, "old": {"by": "adi", "at": now - 30 * 3600}}
    assert invites.clean_saved(saved) == {"ben": {"by": "adi", "at": now}}
    assert invites.clean_saved(["not", "a", "dict"]) == {}


# ---------------------------------------------------------------- security review fixes

def test_a_kick_isnt_undone_by_an_old_invite(user):
    adi, ben = private_group_and_ben(user)
    ben.line(f"/join {GROUP}")
    ben.expect_text("Request sent")
    adi.line("/invite Ben")
    ben.expect(is_invite)
    adi.line("/approve Ben")                              # in another way: the invite is used up too
    adi.expect_text("Ben can now join")
    assert state.groups[KEY]["invites"] == {}
    adi.line("/kick Ben")
    ben.expect_text("kicked", kind="error")
    ben.line(f"/join {GROUP}")
    ben.expect_text("Request sent")
    assert "ben" not in state.groups[KEY]["members"]


def test_a_kicked_member_loses_an_invite_from_before(user):
    adi, ben = private_group_and_ben(user)
    with state.lock:   # (an invite left from before they were a member)
        state.groups[KEY]["members"].append("ben")
        state.groups[KEY]["invites"]["ben"] = {"by": "adi", "at": time.time()}
    adi.line("/kick Ben")
    ben.expect_text("kicked", kind="error")
    assert state.groups[KEY]["invites"] == {}


def test_a_demoted_admins_invites_dont_come_back_with_a_promotion(user):
    adi, ben, cat = user("Adi"), user("Ben"), user("Cat")
    make_group(adi, private=True)
    with state.lock:
        state.groups[KEY]["members"].append("ben")
        state.groups[KEY]["admins"].append("ben")
        state.groups[KEY]["invites"]["cat"] = {"by": "ben", "at": time.time()}
    adi.line("/demote Ben")
    adi.expect_text("no longer an admin")
    assert state.groups[KEY]["invites"] == {}


def test_inviting_the_same_person_again_has_to_wait_a_minute(user):
    adi, ben = private_group_and_ben(user)
    adi.line("/invite Ben")
    ben.expect(is_invite)
    adi.line("/invite Ben")
    adi.expect_text("just invited", kind="error")


def test_one_person_has_at_most_so_many_invites_waiting(user, monkeypatch):
    monkeypatch.setattr(config, "GROUP_INVITES_PER_PERSON", 1)
    adi, ben = private_group_and_ben(user)
    give_tokens("Adi", 500)
    adi.line("/invite Ben")
    ben.expect(is_invite)
    adi.line("/create Fries")
    adi.expect_text("Created")
    enter_room(adi)
    adi.line("/invite Ben")
    adi.expect_text("already has 1 group invite", kind="error")


def test_invites_of_accounts_that_are_gone_are_forgotten(user):
    adi, ben = private_group_and_ben(user)
    with state.lock:
        state.groups[KEY]["invites"]["ghost"] = {"by": "adi", "at": time.time()}
        state.groups[KEY]["invites"]["ben"] = {"by": "nobody", "at": time.time()}
    ben.line("/invites")
    ben.expect_text("No group invites")
    assert state.groups[KEY]["invites"] == {}
