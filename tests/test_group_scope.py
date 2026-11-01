"""
👥 Group commands work only inside the group: /kick, /bank, /leave... act on the group whose chat you're in,
and anywhere else they answer one clear line. /create and /join work from anywhere.

The website's Groups screen sends the same /command with an optional "group" field on the line packet:
the server then runs it for that group (only if you're a member), without moving you out of your chat.
"""
import pytest

from chatserver import state, wars
from test_groups import GROUP, KEY, enter_room, give_tokens, group_with_members, make_group, saw_chat

pytestmark = pytest.mark.integration

GROUP_ONLY = ["/kick Ben", "/ban Ben", "/unban Ben", "/mute Ben", "/unmute Ben", "/promote Ben", "/demote Ben",
              "/approve Ben", "/reject Ben", "/bank", "/donate 5", "/upgrade income", "/groupemoji 🍟",
              "/personality pirate", "/disband", "/leave", "/members", "/requests", "/war Fries"]


def button(client, text, group=KEY):
    """What the website's Groups screen sends: the command, and which group it's for."""
    client.send({"type": "line", "text": text, "group": group})


@pytest.mark.parametrize("line", GROUP_ONLY)
def test_group_commands_from_the_lobby_say_to_open_the_group_chat(user, line):
    adi = user("Adi")
    adi.line(line)
    command = line.split()[0]
    adi.expect_text(f"Open the group's chat to use {command}", kind="error")


def test_a_group_command_acts_on_the_group_youre_in_not_another_one(user):
    adi, ben = group_with_members(user, "Adi", "Ben")   # Ben is in Potatoes
    give_tokens("Adi", 500)
    adi.line("/create Fries")
    adi.expect_text("Created")
    enter_room(adi)
    adi.line("/kick Ben")                               # in Fries' chat: acts on Fries, where Ben isn't
    adi.expect_text("isn't in this group", kind="error")
    assert "ben" in state.groups[KEY]["members"]


def test_create_and_join_work_from_inside_a_group(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    give_tokens("Ben", 500)
    ben.line("/create Fries")
    ben.expect_text("Created")
    enter_room(ben)
    ben.line(f"/join {GROUP}")
    enter_room(ben)
    assert state.online["ben"].room == KEY


def test_approve_takes_no_other_group_from_outside(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, private=True)
    ben.line(f"/join {GROUP}")
    adi.expect_text("Ben wants to join", kind="event")
    adi.line("/lobby")
    enter_room(adi)
    adi.line(f"/approve Ben {GROUP}")                   # the old way, from the lobby
    adi.expect_text("Open the group's chat to use /approve", kind="error")
    assert "ben" not in state.groups[KEY]["members"]
    adi.line(f"/join {GROUP}")
    enter_room(adi)
    adi.line("/approve Ben")
    adi.expect_text("Ben can now join")


def test_the_join_request_notice_says_where_to_approve(user):
    adi, ben = user("Adi"), user("Ben")
    make_group(adi, private=True)
    ben.line(f"/join {GROUP}")
    text = adi.expect_text("Ben wants to join", kind="event")["text"]
    assert "/approve Ben" in text and "/reject Ben" in text and "Potatoes" in text
    assert f"/approve Ben {GROUP}" not in text


def test_a_groups_screen_button_acts_for_its_group_and_you_stay_where_you_are(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/lobby")
    enter_room(adi)
    button(adi, "/kick Ben")
    ben.expect_text("kicked", kind="error")
    assert "ben" not in state.groups[KEY]["members"]
    adi.sync()
    assert state.online["adi"].room == "lobby"


def test_a_button_for_a_group_youre_not_in_does_nothing(user):
    adi, ben, cat = group_with_members(user, "Adi", "Ben", "Cat")
    give_tokens("Cat", 500)
    cat.line("/lobby")
    enter_room(cat)
    button(cat, "/donate 50")                            # a member: fine
    cat.expect_text("donated 50")
    with state.lock:
        state.groups[KEY]["members"].remove("cat")
    button(cat, "/donate 50")
    cat.expect_text("You're not in", kind="error")
    assert state.groups[KEY]["bank"] == 50


def test_the_group_field_never_moves_plain_chat_or_other_commands(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    ben.line("/lobby")
    enter_room(ben)
    button(ben, "hello from the lobby")                 # not a command: chat in the room you're in
    ben.sync()
    adi.sync()
    assert not saw_chat(adi, "hello from the lobby")
    button(ben, "/users")                                # not a group command: works as usual
    ben.expect_text("Online now")


def test_leave_by_button_from_another_room_keeps_you_there(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    ben.line("/lobby")
    enter_room(ben)
    button(ben, "/leave")
    ben.expect_text("You left")
    assert "ben" not in state.groups[KEY]["members"]
    assert state.online["ben"].room == "lobby"


def test_pin_by_button_pins_the_groups_topic_not_the_lobbys(user):
    adi = user("Adi")
    make_group(adi)
    adi.line("/lobby")
    enter_room(adi)
    button(adi, "/pin Movie night")
    adi.expect_text("pinned")
    assert state.groups[KEY]["topic"] == "Movie night"
    assert state.lobby_topic == ""


def test_help_in_the_lobby_hides_the_group_commands(user):
    adi = user("Adi")
    adi.line("/help")
    text = adi.expect(lambda m: m.get("kind") == "help")["text"]
    assert "/create" in text and "/join" in text and "/groups" in text and "/topgroups" in text
    for hidden in ("/kick", "/ban", "/bank ", "/donate", "/disband", "/leave", "/approve", "/war"):
        assert hidden not in text, hidden
    assert "🛡️ Group admin" not in text
    assert "group's chat" in text                       # one line says where the rest are


def test_help_in_a_group_shows_them(user):
    adi = user("Adi")
    make_group(adi)
    adi.line("/help")
    text = adi.expect(lambda m: m.get("kind") == "help")["text"]
    for shown in ("/kick", "/ban", "/bank", "/donate", "/disband", "/leave", "/approve", "/war", "/create", "/join"):
        assert shown in text, shown


def test_group_admins_still_manage_from_inside(user):
    adi, ben = group_with_members(user, "Adi", "Ben")
    adi.line("/mute Ben 3")
    adi.expect_text("was muted for 3 min")


def test_war_by_button_looks_at_that_groups_war(user):
    adi = user("Adi")
    make_group(adi)
    adi.line("/lobby")
    enter_room(adi)
    asked = []
    real = wars.war_of
    wars.war_of = lambda key: asked.append(key) or real(key)
    try:
        button(adi, "/war")
        adi.expect_text("isn't at war")
    finally:
        wars.war_of = real
    assert asked == [KEY]
